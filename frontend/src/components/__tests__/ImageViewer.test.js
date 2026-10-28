import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";

import ImageViewer from "../ImageViewer.svelte";

const filePath = "folder/cover.jpg";

/**
 * @param {number} status
 * @param {string} [statusText]
 */
function imageResponse(status, statusText = "OK") {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    blob: async () => new Blob(["image"], { type: "image/jpeg" }),
  };
}

describe("ImageViewer", () => {
  beforeEach(() => {
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:image-1"),
      revokeObjectURL: vi.fn(),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads the image through the API", async () => {
    const fetchMock = vi.fn().mockResolvedValue(imageResponse(200));
    vi.stubGlobal("fetch", fetchMock);

    render(ImageViewer, { props: { filePath } });

    expect(screen.getByText("Loading image...")).toBeTruthy();
    const image = await screen.findByRole("img", { name: "cover.jpg" });
    expect(image.getAttribute("src")).toBe("blob:image-1");
    expect(screen.getByText("cover.jpg")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/image?path=${encodeURIComponent(filePath)}`,
    );
    expect(URL.createObjectURL).toHaveBeenCalled();
  });

  it("shows the error and retries the load", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(imageResponse(500, "Server Error"))
      .mockResolvedValueOnce(imageResponse(200));
    vi.stubGlobal("fetch", fetchMock);

    render(ImageViewer, { props: { filePath } });

    expect(await screen.findByText("Failed to load image")).toBeTruthy();
    expect(screen.getByText("Failed to load image: Server Error")).toBeTruthy();

    await fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() =>
      expect(screen.getByRole("img", { name: "cover.jpg" })).toBeTruthy(),
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("opens and closes the full-size view", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(imageResponse(200)));
    const { container } = render(ImageViewer, { props: { filePath } });
    await screen.findByRole("img", { name: "cover.jpg" });

    await fireEvent.click(screen.getByTitle("View full size"));

    expect(
      screen.getByRole("img", { name: "Full size cover art" }),
    ).toBeTruthy();

    await fireEvent.click(screen.getByTitle("Close"));

    expect(
      screen.queryByRole("img", { name: "Full size cover art" }),
    ).toBeNull();
    expect(container.querySelector(".full-image-modal")).toBeNull();
  });

  it("closes the full-size view on an overlay click", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(imageResponse(200)));
    const { container } = render(ImageViewer, { props: { filePath } });
    await screen.findByRole("img", { name: "cover.jpg" });
    await fireEvent.click(screen.getByTitle("View full size"));

    const modal = /** @type {HTMLElement} */ (
      container.querySelector(".full-image-modal")
    );
    await fireEvent.click(modal);

    expect(container.querySelector(".full-image-modal")).toBeNull();
  });
});
