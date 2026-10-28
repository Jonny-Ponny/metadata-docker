#!/bin/bash
set -e

# Dependency management

PLUGIN_DIR="/app/addons"
USER_HOME="/app"
USER_SITE="/app/.local"

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

# Application code is root-owned and not writable by the runtime user. Prevent
# Python from trying to create __pycache__ files under /app.
export PYTHONDONTWRITEBYTECODE=1

# Root mode is all-or-nothing. A mixed configuration (for example PUID=1000,
# PGID=0) leaves the runtime user in the root group, so it must not be treated
# as unprivileged: it would still run addon dependency installation and chown
# the library to PUID:root. Reject it instead of silently running root-like.
if [ "$PUID" = "0" ] && [ "$PGID" = "0" ]; then
    RUN_AS_ROOT=1
elif [ "$PUID" = "0" ] || [ "$PGID" = "0" ]; then
    echo "ERROR: PUID and PGID must both be 0 (run as root) or both non-zero."
    echo "       Refusing to start with PUID=$PUID and PGID=$PGID."
    exit 1
else
    RUN_AS_ROOT=0
fi

# User/Group setup
# Default to an unprivileged user so the container does not run as root unless
# explicitly asked to (PUID=0 and PGID=0).
if [ "$RUN_AS_ROOT" = "1" ]; then
    echo "PUID/PGID set to 0, running as root"
    USER_NAME=root
else
    echo "Setting user to PUID:$PUID and PGID:$PGID"

    if getent group "$PGID" > /dev/null 2>&1; then
        GROUP_NAME=$(getent group "$PGID" | cut -d: -f1)
    else
        GROUP_NAME="appgroup"
        addgroup -g "$PGID" "$GROUP_NAME"
    fi

    if getent passwd "$PUID" > /dev/null 2>&1; then
        USER_NAME=$(getent passwd "$PUID" | cut -d: -f1)
        usermod -g "$GROUP_NAME" "$USER_NAME"
    else
        USER_NAME="appuser"
        adduser -u "$PUID" -G "$GROUP_NAME" -D -H "$USER_NAME"
    fi
fi

# Addon dependencies are installed with --user into this directory. It is the
# only part of /app the runtime user needs to write to.
mkdir -p "$USER_SITE"
chown -R "$PUID":"$PGID" "$USER_SITE" || \
    echo "WARNING: could not change ownership of $USER_SITE; addon dependency installation may fail"

install_requirements() {
    local req_file="$1"
    local plugin_name="$2"

    # Never execute addon dependencies as root. Root mode skips the whole scan
    # below, but keep this guard in case the function is reused.
    if [ "$RUN_AS_ROOT" = "1" ]; then
        echo "Skipping dependencies for '$plugin_name': runtime addon dependency installation is disabled when running as root."
        return
    fi

    # Read dependencies (skip empty lines and comments)
    mapfile -t deps < <(grep -v '^[[:space:]]*$' "$req_file" | grep -v '^[[:space:]]*#')

    if [ ${#deps[@]} -eq 0 ]; then
        echo "Requirements file for '$plugin_name' is empty or only comments. Skipping."
        return
    fi

    echo ""
    echo "----------------------------------------"
    echo "Installing dependencies for $plugin_name:"
    local line_num=1
    for dep in "${deps[@]}"; do
        echo "  $line_num. $dep"
        ((line_num++))
    done
    echo "----------------------------------------"

    # Install as the runtime user, never as root. --user writes to USER_SITE;
    # gunicorn uses the same HOME/PYTHONUSERBASE below so it can import them.
    if gosu "$USER_NAME" env HOME="$USER_HOME" PYTHONUSERBASE="$USER_SITE" \
        pip install --user --no-cache-dir -r "$req_file"; then
        echo "Finished installing dependencies for $plugin_name."
    else
        echo "ERROR: Failed to install dependencies for $plugin_name."
    fi
    echo "----------------------------------------"
    echo ""
}

if [ "$RUN_AS_ROOT" = "1" ]; then
    echo ""
    echo "WARNING: Running as root. Runtime addon dependency installation is disabled."
    echo "WARNING: Preinstall addon dependencies in a custom image or use a non-root PUID/PGID."
    echo ""
elif [ -d "$PLUGIN_DIR" ]; then
    echo "Scanning for plugin dependencies in ${PLUGIN_DIR}..."

    # catches any file ending with "requirements.txt"
    # - Flat: /app/addons/discogs_requirements.txt
    # - Subfolder: /app/addons/plugin1/plugin1_requirements.txt
    # - Subfolder: /app/addons/plugin2/requirements.txt
    while IFS= read -r -d '' req_file; do
        parent_dir=$(dirname "$req_file")

        # --- Determine plugin name ---
        if [ "$parent_dir" = "$PLUGIN_DIR" ]; then
            # Flat file: extract name before "_requirements.txt"
            filename=$(basename "$req_file")
            plugin_name="${filename%_requirements.txt}"

            # Safety check: if stripping didn't change the name, it's an unexpected file
            if [ "$plugin_name" = "$filename" ]; then
                echo "Ignoring unexpected flat file: $filename (must end with _requirements.txt)"
                continue
            fi
        else
            # Subfolder: use the immediate parent folder name as the plugin name
            # Example: /app/addons/plugin1/foo_requirements.txt -> "plugin1"
            plugin_name=$(basename "$parent_dir")
        fi

        install_requirements "$req_file" "$plugin_name"

    done < <(find "$PLUGIN_DIR" -type f -name "*requirements.txt" -print0 2>/dev/null)

    echo "Plugin dependency installation complete."
else
    echo "No addons directory found at ${PLUGIN_DIR}, skipping plugin dependency installation."
fi

# Running fully as root keeps the previous behaviour of not touching library/log
# ownership.
if [ "$RUN_AS_ROOT" = "1" ]; then
    echo "Starting gunicorn as root..."
    exec gunicorn --bind 0.0.0.0:${CONTAINER_PORT:-5000} --workers 1 --threads 8 \
        --no-control-socket app:app
fi

# Change ownership so the unprivileged user can read/write the library and logs.
# Do not touch /app: application code must stay root-owned and immutable. The
# addons mount is read-only, so it is left alone as well.
for dir in /music /logs; do
    chown -R "$PUID":"$PGID" "$dir" || echo "WARNING: could not change ownership of $dir, continuing"
done

echo "Starting gunicorn as user $USER_NAME..."
# The control socket defaults to $HOME/.gunicorn, but /app is root-owned and
# must stay read-only for the runtime user. The app does not use gunicornc.
exec gosu "$USER_NAME" env HOME="$USER_HOME" PYTHONUSERBASE="$USER_SITE" \
    PATH="$USER_SITE/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 \
    gunicorn --bind 0.0.0.0:${CONTAINER_PORT:-5000} --workers 1 --threads 8 \
    --no-control-socket app:app
