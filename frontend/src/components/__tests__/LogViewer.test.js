import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";

import LogViewer from "../LogViewer.svelte";
import { toast } from "../../stores/toast.store.js";
import { resetDialogStack, topDialog } from "../../utils/focus.utils.js";
import { isOverlayOpen } from "../../stores/keyboard.store.js";

const entries = [
  { timestamp: "10:00:00", level: "INFO", message: "Server started" },
  { timestamp: "10:00:05", level: "ERROR", message: "Disk full" },
  { raw: "continuation line" },
];

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

/**
 * @param {unknown[]} [logs]
 */
function stubLogs(logs = entries) {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { logs }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/**
 * @param {string} call
 */
function urlOf(call) {
  return String(call);
}

describe("LogViewer", () => {
  beforeEach(() => {
    resetDialogStack();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    toast.clear();
  });

  it("renders nothing and does not fetch while closed", () => {
    const fetchMock = stubLogs();

    render(LogViewer, { props: { isOpen: false, onClose: vi.fn() } });

    expect(screen.queryByText("Application Logs")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("fetches and renders the log entries", async () => {
    const fetchMock = stubLogs();

    render(LogViewer, { props: { isOpen: true, onClose: vi.fn() } });

    expect(await screen.findByText("Server started")).toBeTruthy();
    expect(screen.getByText("[10:00:05]")).toBeTruthy();
    expect(screen.getByText("[ERROR]")).toBeTruthy();
    expect(screen.getByText("continuation line")).toBeTruthy();
    expect(screen.getByText("Showing 3 entries")).toBeTruthy();
    expect(urlOf(fetchMock.mock.calls[0][0])).toBe("/api/logs?lines=100");
  });

  it("shows the empty state", async () => {
    stubLogs([]);

    render(LogViewer, { props: { isOpen: true, onClose: vi.fn() } });

    expect(await screen.findByText("No logs to display")).toBeTruthy();
  });

  it("requests more lines and a level filter", async () => {
    const fetchMock = stubLogs();

    render(LogViewer, { props: { isOpen: true, onClose: vi.fn() } });
    await screen.findByText("Server started");

    const [linesSelect, levelSelect] = screen.getAllByRole("combobox");
    await fireEvent.change(linesSelect, { target: { value: "500" } });
    expect(urlOf(fetchMock.mock.calls.at(-1)?.[0])).toBe("/api/logs?lines=500");

    await fireEvent.change(levelSelect, { target: { value: "ERROR" } });
    expect(urlOf(fetchMock.mock.calls.at(-1)?.[0])).toBe(
      "/api/logs?lines=500&level=ERROR",
    );
    expect(await screen.findByText(/Level: ERROR/)).toBeTruthy();
  });

  it("searches and clears the search", async () => {
    const fetchMock = stubLogs();

    render(LogViewer, { props: { isOpen: true, onClose: vi.fn() } });
    await screen.findByText("Server started");

    const search = screen.getByPlaceholderText("Search logs...");
    await fireEvent.input(search, { target: { value: "disk" } });

    expect(urlOf(fetchMock.mock.calls.at(-1)?.[0])).toBe(
      "/api/logs?lines=100&search=disk",
    );
    expect(await screen.findByText(/Search: "disk"/)).toBeTruthy();

    await fireEvent.click(screen.getByTitle("Clear search"));

    expect(urlOf(fetchMock.mock.calls.at(-1)?.[0])).toBe("/api/logs?lines=100");
    expect(screen.queryByTitle("Clear search")).toBeNull();
  });

  it("shows an error and retries the request", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(500, { error: "Log file missing" }))
      .mockResolvedValueOnce(jsonResponse(200, { logs: entries }));
    vi.stubGlobal("fetch", fetchMock);

    render(LogViewer, { props: { isOpen: true, onClose: vi.fn() } });

    expect(await screen.findByText("Log file missing")).toBeTruthy();

    await fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Server started")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("clears the logs on the server", async () => {
    const fetchMock = stubLogs();

    render(LogViewer, { props: { isOpen: true, onClose: vi.fn() } });
    await screen.findByText("Server started");

    await fireEvent.click(screen.getByRole("button", { name: "Clear" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/logs/clear", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      }),
    );
    expect(await screen.findByText("No logs to display")).toBeTruthy();
    expect(get(toast).at(-1)?.message).toBe("Logs cleared successfully");
  });

  it("reports a failed clear", async () => {
    const fetchMock = stubLogs();

    render(LogViewer, { props: { isOpen: true, onClose: vi.fn() } });
    await screen.findByText("Server started");
    fetchMock.mockResolvedValueOnce(
      jsonResponse(500, { error: "Permission denied" }),
    );

    await fireEvent.click(screen.getByRole("button", { name: "Clear" }));

    await waitFor(() =>
      expect(get(toast).at(-1)?.message).toBe("Permission denied"),
    );
  });

  it("downloads the current entries as a log file", async () => {
    stubLogs();
    const createObjectURL = vi.fn((/** @type {Blob} */ _blob) => "blob:logs");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});

    render(LogViewer, { props: { isOpen: true, onClose: vi.fn() } });
    await screen.findByText("Server started");

    await fireEvent.click(screen.getByRole("button", { name: "Download" }));

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    const blob = /** @type {Blob} */ (createObjectURL.mock.calls[0][0]);
    expect(await blob.text()).toBe(
      "[10:00:00] [INFO] Server started\n[10:00:05] [ERROR] Disk full\ncontinuation line",
    );
    expect(click).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:logs");
  });

  it("schedules a 5 second interval for auto-refresh", async () => {
    stubLogs();
    const setIntervalSpy = vi.spyOn(globalThis, "setInterval");
    const clearIntervalSpy = vi.spyOn(globalThis, "clearInterval");

    render(LogViewer, { props: { isOpen: true, onClose: vi.fn() } });
    await screen.findByText("Server started");

    const checkbox = screen.getByRole("checkbox");
    await fireEvent.click(checkbox);

    expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), 5000);

    await fireEvent.click(checkbox);

    expect(clearIntervalSpy).toHaveBeenCalled();
  });

  it("leaves the dialog stack when it closes", async () => {
    // Reported after using the Help modal's Logs button: the viewer registered
    // itself but could never unregister, because its cleanup read `panel` after
    // the element had been unbound. The stale entry kept `isOverlayOpen()` true
    // forever, so every shortcut stopped working and closing a later dialog
    // could leave the page `inert`.
    stubLogs();
    const { rerender } = render(LogViewer, {
      props: { isOpen: true, onClose: vi.fn() },
    });
    await screen.findByText("Server started");
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(topDialog()?.getAttribute("aria-label")).toBe("Application logs");
    expect(isOverlayOpen()).toBe(true);

    await rerender({ isOpen: false, onClose: vi.fn() });
    await new Promise((resolve) => setTimeout(resolve, 20));

    // A stale entry would make this dialog the "topmost" one forever, so every
    // shortcut stayed off and the next Escape tried to close it again.
    expect(topDialog()).toBeNull();
    expect(isOverlayOpen()).toBe(false);
    expect(document.querySelector("[inert]")).toBeNull();
  });

  it("returns focus to the control that opened it", async () => {
    stubLogs();
    const trigger = document.createElement("button");
    trigger.textContent = "Open logs";
    document.body.appendChild(trigger);
    trigger.focus();

    const { rerender } = render(LogViewer, {
      props: { isOpen: true, onClose: vi.fn() },
    });
    await screen.findByText("Server started");
    await new Promise((resolve) => setTimeout(resolve, 20));

    await rerender({ isOpen: false, onClose: vi.fn() });

    expect(document.activeElement).toBe(trigger);
    trigger.remove();
  });

  it("closes from Escape, the header button, the footer and the overlay", async () => {
    stubLogs();
    const onClose = vi.fn();
    const { container } = render(LogViewer, {
      props: { isOpen: true, onClose },
    });
    await screen.findByText("Server started");

    await fireEvent.keyDown(window, { key: "Escape" });
    await fireEvent.click(screen.getByTitle("Close (Esc)"));
    await fireEvent.click(screen.getByRole("button", { name: "Close" }));

    const overlay = /** @type {HTMLElement} */ (
      container.querySelector(".log-modal-overlay")
    );
    await fireEvent.click(overlay);

    expect(onClose).toHaveBeenCalledTimes(4);
  });

  it("does not close when the dialog body is clicked", async () => {
    stubLogs();
    const onClose = vi.fn();
    const { container } = render(LogViewer, {
      props: { isOpen: true, onClose },
    });
    await screen.findByText("Server started");

    const dialog = /** @type {HTMLElement} */ (
      container.querySelector(".log-modal")
    );
    await fireEvent.click(dialog);

    expect(onClose).not.toHaveBeenCalled();
  });
});
