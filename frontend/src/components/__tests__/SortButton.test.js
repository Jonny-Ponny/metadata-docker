import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/svelte";
import { get } from "svelte/store";

import SortButton from "../SortButton.svelte";
import { sortConfig } from "../../utils/sort.utils.js";

describe("SortButton", () => {
  beforeEach(() => {
    sortConfig.set({ by: "name", direction: "asc" });
  });

  afterEach(() => {
    sortConfig.set({ by: "name", direction: "asc" });
  });

  it("shows the active sort field", () => {
    render(SortButton);

    expect(screen.getByRole("button", { name: /sort by name/i })).toBeTruthy();
  });

  it("opens the menu and selects another field", async () => {
    render(SortButton);

    await fireEvent.click(
      screen.getByRole("button", { name: /sort by name/i }),
    );
    expect(screen.getByRole("button", { name: "Created" })).toBeTruthy();

    await fireEvent.click(screen.getByRole("button", { name: "Created" }));

    expect(get(sortConfig)).toEqual({ by: "created", direction: "asc" });
    expect(screen.queryByRole("button", { name: "Created" })).toBeNull();
    expect(
      screen.getByRole("button", { name: /sort by created/i }),
    ).toBeTruthy();
  });

  it("marks the selected option as active", async () => {
    render(SortButton);

    await fireEvent.click(
      screen.getByRole("button", { name: /sort by name/i }),
    );

    expect(
      screen.getByRole("button", { name: "Name" }).classList.contains("active"),
    ).toBe(true);
  });

  it("toggles the direction and rotates the arrow", async () => {
    render(SortButton);

    const toggle = screen.getByTitle("Toggle sort direction");
    await fireEvent.click(toggle);

    expect(get(sortConfig).direction).toBe("desc");
    expect(toggle.querySelector("svg")?.getAttribute("style")).toContain(
      "rotate(180deg)",
    );
  });

  it("closes the menu on an outside click", async () => {
    render(SortButton);

    await fireEvent.click(
      screen.getByRole("button", { name: /sort by name/i }),
    );
    expect(screen.getByRole("button", { name: "Name" })).toBeTruthy();

    await fireEvent.click(document.body);

    expect(screen.queryByRole("button", { name: "Name" })).toBeNull();
  });
});
