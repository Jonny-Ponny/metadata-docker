import { describe, expect, it } from "vitest";

import { generateFullTheme } from "../color.utils.js";

const colors = {
  "color-primary": "#fd7d05",
  "color-badge-audio": "#fd7d05",
  "color-badge-image": "#6666ff",
  "color-badge-text": "#2e7d32",
};

describe("generateFullTheme", () => {
  it("keeps the base colours", () => {
    const theme = generateFullTheme(colors);

    expect(theme["--color-primary"]).toBe("#fd7d05");
    expect(theme["--color-badge-audio"]).toBe("#fd7d05");
    expect(theme["--color-badge-image"]).toBe("#6666ff");
    expect(theme["--color-badge-text"]).toBe("#2e7d32");
  });

  it("emits every CSS variable the app expects", () => {
    const theme = generateFullTheme(colors);

    expect(Object.keys(theme).sort()).toEqual(
      [
        "--color-primary",
        "--color-primary-focus",
        "--color-primary-dark",
        "--color-primary-dark-focus",
        "--color-primary-transparent",
        "--color-primary-transparent-dark",
        "--color-lrc-playing-transparent",
        "--color-badge-audio",
        "--color-badge-audio-dark",
        "--color-badge-audio-background",
        "--color-badge-audio-background-dark",
        "--color-badge-image",
        "--color-badge-image-dark",
        "--color-badge-image-background",
        "--color-badge-image-background-dark",
        "--color-badge-text",
        "--color-badge-text-dark",
        "--color-badge-text-background",
        "--color-badge-text-background-dark",
      ].sort(),
    );
  });

  it("derives lighter and more saturated variants", () => {
    const theme = generateFullTheme(colors);

    expect(theme["--color-primary-focus"]).not.toBe("#fd7d05");
    expect(theme["--color-primary-dark"]).not.toBe("#fd7d05");
    expect(theme["--color-primary-dark-focus"]).not.toBe(
      theme["--color-primary-dark"],
    );
    expect(theme["--color-badge-audio-dark"]).not.toBe("#fd7d05");
  });

  it("appends the alpha suffixes used by the stylesheet", () => {
    const theme = generateFullTheme(colors);

    expect(theme["--color-primary-transparent"]).toBe("#fd7d0540");
    expect(theme["--color-primary-transparent-dark"]).toBe(
      `${theme["--color-primary-dark"]}30`,
    );
    expect(theme["--color-lrc-playing-transparent"]).toBe("#fd7d050d");
    expect(theme["--color-badge-image-background"]).toBe("#6666ff26");
    expect(theme["--color-badge-text-background"]).toBe("#2e7d3226");
  });

  it("lightens dark colours by ten percent in dark mode", () => {
    const theme = generateFullTheme({
      ...colors,
      "color-primary": "#000000",
    });

    expect(theme["--color-primary-dark"]).toBe("#1a1a1a");
  });

  it("keeps white white when lightening", () => {
    const theme = generateFullTheme({
      ...colors,
      "color-primary": "#ffffff",
    });

    expect(theme["--color-primary-dark"]).toBe("#ffffff");
    expect(theme["--color-primary-focus"]).toBe("#ffffff");
  });
});
