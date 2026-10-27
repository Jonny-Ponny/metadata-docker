import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/svelte";

import HelpModal from "../HelpModal.svelte";

describe("HelpModal", () => {
  it("renders nothing while closed", () => {
    render(HelpModal, { props: { isOpen: false, onClose: vi.fn() } });

    expect(screen.queryByText("Help & Information")).toBeNull();
  });

  it("opens on the app basics tab", () => {
    render(HelpModal, { props: { isOpen: true, onClose: vi.fn() } });

    expect(screen.getByText("Help & Information")).toBeTruthy();
    expect(screen.getByText("File Browser")).toBeTruthy();
    expect(screen.getByText("Keyboard Shortcuts")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "App Basics" }).className,
    ).toContain("active");
  });

  it("switches to the tag reference tab", async () => {
    render(HelpModal, { props: { isOpen: true, onClose: vi.fn() } });

    await fireEvent.click(
      screen.getByRole("button", { name: "Tag Information" }),
    );

    expect(screen.getByText("Common Audio Tags")).toBeTruthy();
    expect(screen.getByText("ID3v2 (MP3/WAV/AIFF) Tags")).toBeTruthy();
    expect(screen.queryByText("File Browser")).toBeNull();
    expect(
      screen.getByRole("button", { name: "Tag Information" }).className,
    ).toContain("active");
  });

  it("closes on Escape while open", async () => {
    const onClose = vi.fn();
    render(HelpModal, { props: { isOpen: true, onClose } });

    await fireEvent.keyDown(window, { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("ignores Escape while closed", async () => {
    const onClose = vi.fn();
    render(HelpModal, { props: { isOpen: false, onClose } });

    await fireEvent.keyDown(window, { key: "Escape" });

    expect(onClose).not.toHaveBeenCalled();
  });

  it("closes from the header button, the footer button and the overlay", async () => {
    const onClose = vi.fn();
    const { container } = render(HelpModal, {
      props: { isOpen: true, onClose },
    });

    await fireEvent.click(screen.getByTitle("Close (Esc)"));
    await fireEvent.click(screen.getByRole("button", { name: "Close" }));

    const overlay = /** @type {HTMLElement} */ (
      container.querySelector(".help-modal-overlay")
    );
    await fireEvent.click(overlay);

    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it("does not close when the dialog body is clicked", async () => {
    const onClose = vi.fn();
    const { container } = render(HelpModal, {
      props: { isOpen: true, onClose },
    });

    const dialog = /** @type {HTMLElement} */ (
      container.querySelector(".help-modal")
    );
    await fireEvent.click(dialog);

    expect(onClose).not.toHaveBeenCalled();
  });

  it("shows the version and a short commit link", () => {
    render(HelpModal, {
      props: {
        isOpen: true,
        onClose: vi.fn(),
        currentVersion: "v1.1.0",
        gitSha: "abcdef1234567890",
      },
    });

    expect(screen.getByText("v1.1.0")).toBeTruthy();
    const commit = screen.getByRole("link", { name: "abcdef1" });
    expect(commit.getAttribute("href")).toBe(
      "https://github.com/Jonny-Ponny/metadata-docker/commit/abcdef1234567890",
    );
    expect(commit.getAttribute("title")).toBe(
      "Built from commit abcdef1234567890",
    );
  });

  it("omits the commit link when the sha is unknown", () => {
    render(HelpModal, {
      props: {
        isOpen: true,
        onClose: vi.fn(),
        currentVersion: "v1.1.0",
        gitSha: "unknown",
      },
    });

    expect(screen.getByText("v1.1.0")).toBeTruthy();
    expect(screen.queryByTitle(/Built from commit/)).toBeNull();
  });

  it("closes and opens the log viewer from the footer", async () => {
    const onClose = vi.fn();
    const openLogs = vi.fn();
    window.addEventListener("openLogs", openLogs);
    render(HelpModal, { props: { isOpen: true, onClose } });

    await fireEvent.click(screen.getByRole("button", { name: "Logs" }));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(openLogs).toHaveBeenCalledTimes(1);
    window.removeEventListener("openLogs", openLogs);
  });
});
