import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/svelte";
import { tick } from "svelte";

import UploadTray from "../UploadTray.svelte";
import { upload } from "../../stores/upload.store.js";

/**
 * @param {Partial<import("../../stores/upload.store.js").UploadState>} [patch]
 */
function setState(patch = {}) {
  upload.set({
    phase: "idle",
    totalBytes: 0,
    doneBytes: 0,
    totalFiles: 0,
    doneFiles: 0,
    scanFiles: 0,
    scanBytes: 0,
    uploaded: 0,
    skipped: 0,
    failed: 0,
    queued: 0,
    currentName: "",
    failures: [],
    blocked: null,
    message: "",
    bytesPerSecond: 0,
    fatal: false,
    conflict: "skip-identical",
    ...patch,
  });
}

/**
 * @param {string} name
 * @param {boolean} [retryable]
 * @returns {import("../../stores/upload.store.js").UploadFailure}
 */
function failure(name, retryable = true) {
  return {
    name,
    reason: "Network error",
    retryable,
    file: new File([], name),
    relativePath: name,
    targetPath: `folder/${name}`,
  };
}

describe("UploadTray", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    setState();
  });

  afterEach(() => {
    setState();
    vi.useRealTimers();
  });

  it("renders nothing while idle", () => {
    const { container } = render(UploadTray);

    expect(container.querySelector(".upload-tray")).toBeNull();
  });

  it("reports the folder scan while preparing", async () => {
    render(UploadTray);
    setState({ phase: "preparing", scanFiles: 12, scanBytes: 2048 });
    await tick();

    expect(screen.getByText("Reading folder…")).toBeTruthy();
    expect(screen.getByText("12 files · 2.0 KB found")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeTruthy();
  });

  it("shows byte progress and remaining time while running", async () => {
    render(UploadTray);
    setState({
      phase: "running",
      totalBytes: 1000,
      doneBytes: 500,
      totalFiles: 4,
      doneFiles: 2,
      queued: 1,
      bytesPerSecond: 100,
    });
    await tick();

    const region = screen.getByRole("region", { name: "Upload progress" });
    expect(region.getAttribute("aria-live")).toBe("off");
    expect(screen.getByText("Uploading 50%")).toBeTruthy();
    expect(
      screen.getByText("500 B / 1000 B · 2 / 4 files · ~5 s left · 1 queued"),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeTruthy();
  });

  it("offers to upload anyway when the space check blocks the batch", async () => {
    render(UploadTray);
    setState({
      phase: "blocked",
      message: "Not enough free space in the library.",
    });
    await tick();

    expect(screen.getByText("Not enough free space")).toBeTruthy();
    expect(
      screen.getByText("Not enough free space in the library."),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Upload anyway" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeTruthy();
  });

  it("summarises a successful upload and hides it after ten seconds", async () => {
    render(UploadTray);
    setState({
      phase: "done",
      uploaded: 3,
      skipped: 1,
      totalFiles: 4,
      doneFiles: 4,
    });
    await tick();

    expect(screen.getByText("Upload complete")).toBeTruthy();
    expect(screen.getByText("3 uploaded · 1 skipped")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Dismiss" })).toBeTruthy();

    await vi.advanceTimersByTimeAsync(10_000);

    expect(
      screen.queryByRole("region", { name: "Upload progress" }),
    ).toBeNull();
  });

  it("keeps failures visible and expands their details", async () => {
    render(UploadTray);
    setState({
      phase: "done",
      failed: 2,
      failures: [failure("one.mp3"), failure("two.flac", false)],
    });
    await tick();

    expect(screen.getByText("Upload finished with errors")).toBeTruthy();
    expect(screen.getByText("2 failed")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry 1" })).toBeTruthy();

    const toggle = screen.getByTitle("Show details");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");

    await fireEvent.click(toggle);

    expect(screen.getByTitle("Hide details")).toBeTruthy();
    expect(screen.getByText("one.mp3")).toBeTruthy();
    expect(screen.getAllByText("Network error")).toHaveLength(2);

    await vi.advanceTimersByTimeAsync(10_000);
    expect(
      screen.getByRole("region", { name: "Upload progress" }),
    ).toBeTruthy();
  });

  it("caps the expanded failure list at fifty entries", async () => {
    render(UploadTray);
    setState({
      phase: "done",
      failed: 55,
      failures: Array.from({ length: 55 }, (_, index) =>
        failure(`track-${index}.mp3`),
      ),
    });
    await tick();

    await fireEvent.click(screen.getByTitle("Show details"));

    expect(screen.getByText("and 5 more…")).toBeTruthy();
  });

  it("shows the refresh state with a hide action", async () => {
    render(UploadTray);
    setState({
      phase: "refreshing",
      doneFiles: 2,
      queued: 1,
    });
    await tick();

    expect(screen.getByText("Refreshing library…")).toBeTruthy();
    expect(screen.getByText("2 files saved · 1 queued")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Hide" })).toBeTruthy();
  });

  it("shows a cancelled upload without the retry action", async () => {
    render(UploadTray);
    setState({
      phase: "done",
      message: "Upload cancelled.",
    });
    await tick();

    expect(screen.getByText("Upload cancelled")).toBeTruthy();
    expect(screen.getByText("Upload cancelled.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /retry/i })).toBeNull();
  });
});
