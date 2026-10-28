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
    coverage: {
      provider: "v8",
      reporter: ["text", "text-summary", "html", "lcov"],
      reportsDirectory: "./coverage",
      include: ["src/**/*.{js,svelte}"],
      exclude: ["src/**/__tests__/**", "src/test/**", "src/main.js"],
    },
  },
});
