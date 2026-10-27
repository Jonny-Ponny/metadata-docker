import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";

import Login from "../Login.svelte";
import { authError, isAuthenticated } from "../../stores/auth.store.js";
import { theme } from "../../stores/theme.store.js";

/**
 * @param {number} status
 * @param {Record<string, unknown>} body
 */
function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

describe("Login", () => {
  beforeEach(() => {
    authError.set(null);
    isAuthenticated.set(false);
    theme.set("light");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the credential fields and submit button", () => {
    render(Login);

    expect(screen.getByLabelText("Username")).toBeTruthy();
    expect(screen.getByLabelText("Password")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Login" })).toBeTruthy();
  });

  it("posts the credentials and marks the session authenticated", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        token: "jwt-token",
        username: "alice",
        expires_in: 3600,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(Login);

    await fireEvent.input(screen.getByLabelText("Username"), {
      target: { value: "alice" },
    });
    await fireEvent.input(screen.getByLabelText("Password"), {
      target: { value: "secret" },
    });
    await fireEvent.submit(screen.getByRole("button", { name: "Login" }));

    await waitFor(() => expect(get(isAuthenticated)).toBe(true));
    expect(fetchMock).toHaveBeenCalledWith("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: "alice", password: "secret" }),
    });
    expect(localStorage.getItem("auth_token")).toBe("jwt-token");
  });

  it("shows the backend error and stays logged out", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(401, {
          error: "Invalid credentials",
        }),
      ),
    );
    render(Login);

    await fireEvent.input(screen.getByLabelText("Username"), {
      target: { value: "alice" },
    });
    await fireEvent.input(screen.getByLabelText("Password"), {
      target: { value: "wrong" },
    });
    await fireEvent.submit(screen.getByRole("button", { name: "Login" }));

    expect(await screen.findByText("Invalid credentials")).toBeTruthy();
    expect(get(isAuthenticated)).toBe(false);
    expect(get(authError)).toBe("Invalid credentials");
  });

  it("disables the form while the request is pending", async () => {
    /** @type {(value: unknown) => void} */
    let resolveRequest = () => {};
    const pending = new Promise((resolve) => {
      resolveRequest = resolve;
    });
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(pending));
    render(Login);

    await fireEvent.input(screen.getByLabelText("Username"), {
      target: { value: "alice" },
    });
    await fireEvent.input(screen.getByLabelText("Password"), {
      target: { value: "secret" },
    });
    await fireEvent.submit(screen.getByRole("button", { name: "Login" }));

    const pendingButton = screen.getByRole("button", { name: "Logging in..." });
    expect(/** @type {HTMLButtonElement} */ (pendingButton).disabled).toBe(
      true,
    );
    expect(
      /** @type {HTMLInputElement} */ (screen.getByLabelText("Username"))
        .disabled,
    ).toBe(true);

    resolveRequest(
      jsonResponse(200, { token: "t", username: "alice", expires_in: 60 }),
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Login" })).toBeTruthy(),
    );
  });

  it("toggles the theme from the login screen", async () => {
    render(Login);

    await fireEvent.click(screen.getByRole("button", { name: "Light" }));

    expect(get(theme)).toBe("dark");
  });
});
