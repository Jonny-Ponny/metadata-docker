import { defineConfig } from "vitest/config";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// Component tests are not here yet, but registering the Svelte plugin now
// means the config does not have to change when they are added.
export default defineConfig({
  plugins: [svelte()],
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.js"],
    setupFiles: ["./src/test/setup.js"],
    restoreMocks: true,
  },
});
