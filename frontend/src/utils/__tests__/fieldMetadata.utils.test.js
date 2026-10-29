import { describe, expect, it } from "vitest";

import {
  FIELD_METADATA,
  getFieldDescription,
  getFieldLabel,
} from "../fieldMetadata.utils.js";

describe("fieldMetadata", () => {
  it("returns the human-readable label", () => {
    expect(getFieldLabel("title")).toBe("Title");
    expect(getFieldLabel("albumArtist")).toBe("Album Artist");
    expect(getFieldLabel("picture")).toBe("Cover Art");
    expect(getFieldLabel("lyrics")).toBe("Synced Lyrics");
    expect(getFieldLabel("releaseType")).toBe("Release Type");
    expect(getFieldLabel("comment")).toBe("Comment");
    expect(getFieldLabel("description")).toBe("Description");
  });

  it("falls back to the raw key for unknown fields", () => {
    expect(getFieldLabel("customField")).toBe("customField");
  });

  it("returns descriptions for known fields", () => {
    expect(getFieldDescription("title")).toContain("Song title");
    expect(getFieldDescription("trackNumber")).toBe(
      "The track number on the album",
    );
    expect(getFieldDescription("releaseType")).toContain("album, EP, single");
    expect(getFieldDescription("comment")).toContain("Free-form notes");
    expect(getFieldDescription("description")).toContain("Additional");
  });

  it("returns an empty description for unknown fields", () => {
    expect(getFieldDescription("customField")).toBe("");
  });

  it("keeps every entry complete", () => {
    for (const [key, meta] of Object.entries(FIELD_METADATA)) {
      expect(meta.label, key).toBeTruthy();
      expect(meta.description, key).toBeTruthy();
      expect(getFieldLabel(key)).toBe(meta.label);
      expect(getFieldDescription(key)).toBe(meta.description);
    }
  });
});
