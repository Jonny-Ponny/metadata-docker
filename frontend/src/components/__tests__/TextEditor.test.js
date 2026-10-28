import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";

import TextEditor from "../TextEditor.svelte";
import { toast } from "../../stores/toast.store.js";

const filePath = "folder/notes.txt";

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
 * @param {string} [content]
 */
function stubText(content = "line one\nline two") {
  const fetchMock = vi.fn(
    /**
     * @param {string} url
     * @param {{ method?: string }} [options]
     */
    (url, options = {}) => {
      if (options.method === "POST") {
        return Promise.resolve(jsonResponse(200, { success: true }));
      }
      return Promise.resolve(jsonResponse(200, { content }));
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("TextEditor", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    toast.clear();
  });

  it("loads the file content", async () => {
    const fetchMock = stubText("hello");

    render(TextEditor, { props: { filePath } });

    expect(screen.getByText("Loading…")).toBeTruthy();
    const textarea = await screen.findByRole("textbox");
    expect(/** @type {HTMLTextAreaElement} */ (textarea).value).toBe("hello");
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/text?path=${encodeURIComponent(filePath)}`,
    );
  });

  it("saves the edited content", async () => {
    const fetchMock = stubText();
    render(TextEditor, { props: { filePath } });
    const textarea = await screen.findByRole("textbox");

    await fireEvent.input(textarea, { target: { value: "new content" } });
    await fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/text/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: filePath, content: "new content" }),
      }),
    );
    expect(get(toast).at(-1)?.message).toBe("Text saved");
  });

  it("shows a load error instead of the editor", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(404, { error: "No such file" })),
    );

    render(TextEditor, { props: { filePath } });

    expect(await screen.findByText("No such file")).toBeTruthy();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(get(toast).at(-1)?.message).toBe("No such file");
  });

  it("reports a save failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        /**
         * @param {string} _url
         * @param {{ method?: string }} [options]
         */
        (_url, options = {}) =>
          options.method === "POST"
            ? Promise.resolve(jsonResponse(500, { error: "Disk full" }))
            : Promise.resolve(jsonResponse(200, { content: "text" })),
      ),
    );
    render(TextEditor, { props: { filePath } });
    await screen.findByRole("textbox");

    await fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(get(toast).at(-1)?.message).toBe("Save error: Disk full"),
    );
  });

  it("copies the content to the clipboard", async () => {
    stubText("copy me");
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    render(TextEditor, { props: { filePath } });
    await screen.findByRole("textbox");

    await fireEvent.click(
      screen.getByRole("button", { name: /copy to clipboard/i }),
    );

    expect(writeText).toHaveBeenCalledWith("copy me");
    expect(get(toast).at(-1)?.message).toBe("Copied to clipboard");
  });
});
