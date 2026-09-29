import { resolve } from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// TARGET selects which background entry is bundled; the build script assembles
// the final per-browser dist (manifest + icons) around this output.
const target = process.env.TARGET === "firefox" ? "firefox" : "chromium";

export default defineConfig({
  plugins: [react()],
  root: "extension",
  build: {
    outDir: resolve(__dirname, `extension/dist/${target}`),
    emptyOutDir: true,
    rollupOptions: {
      input: {
        index: resolve(__dirname, "extension/index.html"),
        background: resolve(__dirname, `extension/src/background.${target}.ts`),
      },
      output: {
        entryFileNames: (chunk) => (chunk.name === "background" ? "background.js" : "assets/[name].js"),
        assetFileNames: "assets/[name][extname]",
      },
    },
  },
  test: {
    environment: "jsdom",
    include: ["../tests/extension/**/*.test.ts", "../tests/extension/**/*.test.tsx"],
    globals: true,
  },
});
