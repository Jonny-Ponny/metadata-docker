import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/svelte";

import HelpModal from "../HelpModal.svelte";
import { closeDialog, openDialog } from "../../utils/focus.utils.js";

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

  describe("dialog semantics and focus", () => {
    it("is announced as a modal dialog with a name", () => {
      render(HelpModal, { props: { isOpen: true, onClose: vi.fn() } });

      const dialog = screen.getByRole("dialog", {
        name: "Help and information",
      });

      expect(dialog.getAttribute("aria-modal")).toBe("true");
      expect(dialog.className).toContain("help-modal");
    });

    it("stays open on Escape while another dialog is on top", async () => {
      // Dialogs are mounted while closed and nested (the lyrics editor opens
      // its own edit dialog), so Escape must only close the topmost one.
      const onClose = vi.fn();
      render(HelpModal, { props: { isOpen: true, onClose } });
      const dialog = screen.getByRole("dialog", {
        name: "Help and information",
      });
      const inner = document.createElement("div");
      document.body.appendChild(inner);
      openDialog(inner);
      try {
        await fireEvent.keyDown(dialog, { key: "Escape" });
        expect(onClose).not.toHaveBeenCalled();
      } finally {
        closeDialog(inner);
        inner.remove();
      }
    });

    it("gives focus back to the button that opened it", async () => {
      // Closing used to drop focus, so the next Tab restarted from the top of
      // the page instead of from the control the user came from.
      const trigger = document.createElement("button");
      trigger.textContent = "Help";
      document.body.appendChild(trigger);
      trigger.focus();
      const view = render(HelpModal, {
        props: { isOpen: true, onClose: vi.fn() },
      });
      const dialog = screen.getByRole("dialog", {
        name: "Help and information",
      });
      /** @type {HTMLElement} */ (dialog.querySelector("button")).focus();

      await view.rerender({ isOpen: false, onClose: vi.fn() });

      expect(document.activeElement).toBe(trigger);
      trigger.remove();
    });

    it("wraps Tab from the last control back to the first", async () => {
      // Without the wrap, Tab leaves the dialog and drives the page behind it.
      render(HelpModal, { props: { isOpen: true, onClose: vi.fn() } });
      const dialog = screen.getByRole("dialog", {
        name: "Help and information",
      });
      const stops = [...dialog.querySelectorAll("button, a[href]")].filter(
        (element) => /** @type {HTMLElement} */ (element).tabIndex >= 0,
      );
      const last = /** @type {HTMLElement} */ (stops[stops.length - 1]);
      last.focus();

      await fireEvent.keyDown(last, { key: "Tab" });

      expect(document.activeElement).toBe(stops[0]);
    });
  });
});
