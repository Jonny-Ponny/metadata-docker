#!/bin/bash
set -e

# Dependency management

PLUGIN_DIR="/app/addons"

install_requirements() {
    local req_file="$1"
    local plugin_name="$2"

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

    # Install using pip – if it fails, log but continue (no `set -e` exit)
    if pip install --no-cache-dir -r "$req_file"; then
        echo "Finished installing dependencies for $plugin_name."
    else
        echo "ERROR: Failed to install dependencies for $plugin_name."
    fi
    echo "----------------------------------------"
    echo ""
}

if [ -d "$PLUGIN_DIR" ]; then
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

# User/Group setup

if [ ! -z "$PUID" ] && [ ! -z "$PGID" ]; then
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
    
    chown -R "$PUID":"$PGID" /app /music /logs
    echo "Starting gunicorn as user $USER_NAME..."
    exec gosu "$USER_NAME" env HOME=/app gunicorn --bind 0.0.0.0:${CONTAINER_PORT:-5000} \
    --workers 1 --threads 8 app:app

else
    echo "PUID/PGID not set, running as root"
    exec gunicorn --bind 0.0.0.0:${CONTAINER_PORT:-5000} --workers 1 --threads 8 app:app
fi
