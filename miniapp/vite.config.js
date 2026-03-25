import { defineConfig } from "vite";
import { resolve } from "path";

export default defineConfig({
  root: "static",
  build: {
    outDir: "../static-dist",
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: {
        app: resolve(__dirname, "static/app.js"),
        styles: resolve(__dirname, "static/app.css"),
      },
      output: {
        entryFileNames: "assets/[name]-[hash].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
    // Bundle all CSS into a single file
    cssCodeSplit: false,
  },
  // Dev server proxies API calls to FastAPI
  server: {
    proxy: {
      "/api": "http://localhost:8091",
    },
  },
});
