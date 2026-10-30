import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";

import CoverPreview from "../CoverPreview.svelte";

/**
 * @param {number} status
 * @param {string} [type]
 */
function imageResponse(status, type = "image/png") {
  return {
    ok: status >= 200 && status < 300,
    status,
    blob: async () => new Blob(["cover"], { type }),
  };
}

describe("CoverPreview", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders a data URL directly without a source link", () => {
    const { container } = render(CoverPreview, {
      props: { url: "data:image/png;base64,AAAA", alt: "Album cover" },
    });

    const image = screen.getByRole("img", { name: "Album cover" });
    expect(image.getAttribute("src")).toBe("data:image/png;base64,AAAA");
    expect(container.querySelector(".cover-preview.field")).toBeTruthy();
    expect(container.querySelector(".cover-source")).toBeNull();
  });

  it("shows the placeholder when there is no URL", () => {
    render(CoverPreview, {
      props: { url: null, placeholder: "data:image/png;base64,BBBB" },
    });

    expect(screen.getByRole("img").getAttribute("src")).toBe(
      "data:image/png;base64,BBBB",
    );
  });

  it("loads a remote cover through the preview proxy", async () => {
    const remote = "https://example.test/cover.jpg";
    const fetchMock = vi.fn().mockResolvedValue(imageResponse(200));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:cover"),
      revokeObjectURL: vi.fn(),
    });

    const { container } = render(CoverPreview, {
      props: { url: remote, variant: "result" },
    });

    expect(container.querySelector(".cover-preview.result")).toBeTruthy();
    expect(
      screen
        .getByRole("link", { name: new RegExp(remote) })
        .getAttribute("href"),
    ).toBe(remote);

    await waitFor(() =>
      expect(screen.getByRole("img").getAttribute("src")).toBe("blob:cover"),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/metadata/picture/preview?url=${encodeURIComponent(remote)}`,
      { headers: {} },
    );
  });

  it("shows the natural image size in the tooltip once it loads", async () => {
    const remote = "https://example.test/cover.jpg";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(imageResponse(200)));
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:cover"),
      revokeObjectURL: vi.fn(),
    });

    const { container } = render(CoverPreview, {
      props: { url: remote, variant: "result" },
    });
    const preview = container.querySelector(".cover-preview");

    expect(preview?.getAttribute("title")).toBe(remote);

    const image = await screen.findByRole("img");
    Object.defineProperty(image, "naturalWidth", {
      value: 600,
      configurable: true,
    });
    Object.defineProperty(image, "naturalHeight", {
      value: 450,
      configurable: true,
    });
    await fireEvent.load(image);

    expect(preview?.getAttribute("title")).toBe(`${remote}\n600x450px`);
  });

  it("reads dimensions with the detached image probe", async () => {
    const remote = "https://example.test/cover.jpg";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(imageResponse(200)));
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:cover"),
      revokeObjectURL: vi.fn(),
    });

    class ProbeImage {
      naturalWidth = 320;
      naturalHeight = 320;
      /** @type {(() => void) | null} */
      onload = null;
      /** @type {((event: Event) => void) | null} */
      onerror = null;

      /** @param {string} _value */
      set src(_value) {
        queueMicrotask(() => this.onload?.());
      }
    }
    vi.stubGlobal("Image", ProbeImage);

    const { container } = render(CoverPreview, {
      props: { url: remote, variant: "result" },
    });
    const preview = container.querySelector(".cover-preview");

    await waitFor(() =>
      expect(preview?.getAttribute("title")).toBe(`${remote}\n320x320px`),
    );
  });

  it("shows a failed marker when the remote cover cannot be loaded", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(imageResponse(404)));

    const { container } = render(CoverPreview, {
      props: { url: "https://example.test/missing.jpg" },
    });

    expect(
      await screen.findByRole("img", { name: "Cover preview unavailable" }),
    ).toBeTruthy();
    expect(container.querySelector(".cover-failed")).toBeTruthy();
  });

  it("hides the source link on request", () => {
    const { container } = render(CoverPreview, {
      props: {
        url: "https://example.test/cover.jpg",
        showSourceLink: false,
      },
    });

    expect(container.querySelector(".cover-source")).toBeNull();
  });
});
