import { defineConfig } from "vitest/config";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { svelteTesting } from "@testing-library/svelte/vite";

export default defineConfig({
  // svelteTesting adds the browser resolve condition and the DOM cleanup
  // after every test.
  plugins: [svelte(), svelteTesting()],
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.js"],
    setupFiles: ["./src/test/setup.js"],
    restoreMocks: true,
  },
});
