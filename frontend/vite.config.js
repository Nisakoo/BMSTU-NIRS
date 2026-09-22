import { fileURLToPath, URL } from "node:url";

import { defineConfig } from "vite";

const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8000";
const proxy = {
  "/api": {
    target: backendUrl,
    changeOrigin: true,
  },
};

export default defineConfig({
  root: fileURLToPath(new URL("./src", import.meta.url)),
  server: {
    port: 5173,
    strictPort: true,
    proxy,
  },
  build: {
    outDir: fileURLToPath(new URL("./dist", import.meta.url)),
    emptyOutDir: true,
  },
});
