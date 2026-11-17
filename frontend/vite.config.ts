// Build and test settings for the frontend.
// "npm run build" writes the finished pages to frontend/dist, which the
// backend serves to the app window.
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    // A fake browser page for tests, so no real window is needed.
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    // GitHub's build machines are slower than a normal PC.
    testTimeout: 20_000,
  },
});
