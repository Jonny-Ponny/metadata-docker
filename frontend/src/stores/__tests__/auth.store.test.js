import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";

import {
  authError,
  authToken,
  authUser,
  getAuthHeaders,
  initAuth,
  isAuthenticated,
  login,
  logout,
  tokenExpiry,
} from "../auth.store.js";

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

function resetStore() {
  authToken.set(null);
  authUser.set(null);
  authError.set(null);
  tokenExpiry.set(null);
  isAuthenticated.set(false);
}

describe("auth store", () => {
  beforeEach(() => {
    resetStore();
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("does nothing without a stored session", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await initAuth();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(get(isAuthenticated)).toBe(false);
  });

  it("restores a valid stored session", async () => {
    const expiry = Math.floor(Date.now() / 1000) + 3600;
    localStorage.setItem("auth_token", "stored-token");
    localStorage.setItem("auth_user", "alice");
    localStorage.setItem("token_expiry", String(expiry));
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { valid: true }));
    vi.stubGlobal("fetch", fetchMock);

    await initAuth();

    expect(fetchMock).toHaveBeenCalledWith("/api/validate", {
      headers: { Authorization: "Bearer stored-token" },
    });
    expect(get(isAuthenticated)).toBe(true);
    expect(get(authToken)).toBe("stored-token");
    expect(get(authUser)).toBe("alice");
    expect(get(tokenExpiry)).toBe(expiry);
  });

  it("logs out when the server rejects the stored token", async () => {
    localStorage.setItem("auth_token", "stale-token");
    localStorage.setItem("auth_user", "alice");
    localStorage.setItem(
      "token_expiry",
      String(Math.floor(Date.now() / 1000) + 3600),
    );
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(401, {})));

    await initAuth();

    expect(get(isAuthenticated)).toBe(false);
    expect(localStorage.getItem("auth_token")).toBeNull();
  });

  it("logs out when the stored token expired", async () => {
    localStorage.setItem("auth_token", "old-token");
    localStorage.setItem("auth_user", "alice");
    localStorage.setItem(
      "token_expiry",
      String(Math.floor(Date.now() / 1000) - 10),
    );
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await initAuth();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(get(isAuthenticated)).toBe(false);
    expect(localStorage.getItem("auth_token")).toBeNull();
  });

  it("logs out when validation fails over the network", async () => {
    localStorage.setItem("auth_token", "token");
    localStorage.setItem("auth_user", "alice");
    localStorage.setItem(
      "token_expiry",
      String(Math.floor(Date.now() / 1000) + 3600),
    );
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    await initAuth();

    expect(get(isAuthenticated)).toBe(false);
    expect(localStorage.getItem("auth_token")).toBeNull();
  });

  it("stores the session after a successful login", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        token: "new-token",
        username: "bob",
        expires_in: 3600,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await login("bob", "secret");

    expect(result).toEqual({ success: true });
    expect(fetchMock).toHaveBeenCalledWith("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: "bob", password: "secret" }),
    });
    expect(get(isAuthenticated)).toBe(true);
    expect(get(authToken)).toBe("new-token");
    expect(get(authUser)).toBe("bob");
    expect(localStorage.getItem("auth_token")).toBe("new-token");
    expect(localStorage.getItem("auth_user")).toBe("bob");
    expect(Number(localStorage.getItem("token_expiry"))).toBeGreaterThan(
      Math.floor(Date.now() / 1000),
    );
  });

  it("reports the backend login error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(401, { error: "Bad password" })),
    );

    const result = await login("bob", "wrong");

    expect(result).toEqual({ success: false, error: "Bad password" });
    expect(get(authError)).toBe("Bad password");
    expect(get(isAuthenticated)).toBe(false);
  });

  it("wraps a network login failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    const result = await login("bob", "secret");

    expect(result).toEqual({ success: false, error: "offline" });
    expect(get(authError)).toBe("offline");
  });

  it("clears the session on logout", () => {
    authToken.set("token");
    authUser.set("bob");
    tokenExpiry.set(123);
    isAuthenticated.set(true);
    localStorage.setItem("auth_token", "token");
    localStorage.setItem("auth_user", "bob");
    localStorage.setItem("token_expiry", "123");

    logout();

    expect(get(isAuthenticated)).toBe(false);
    expect(get(authToken)).toBeNull();
    expect(get(authUser)).toBeNull();
    expect(get(tokenExpiry)).toBeNull();
    expect(localStorage.getItem("auth_token")).toBeNull();
    expect(localStorage.getItem("auth_user")).toBeNull();
    expect(localStorage.getItem("token_expiry")).toBeNull();
  });

  it("builds the authorization header only when signed in", () => {
    expect(getAuthHeaders()).toEqual({});

    authToken.set("token");

    expect(getAuthHeaders()).toEqual({ Authorization: "Bearer token" });
  });
});
