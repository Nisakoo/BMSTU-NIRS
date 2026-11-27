import { fileURLToPath, URL } from "node:url";

import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";

const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8000";
const proxy = {
  "/api": {
    target: backendUrl,
    changeOrigin: true,
  },
};

export default defineConfig({
  plugins: [svelte()],
  root: fileURLToPath(new URL("./src/entry/", import.meta.url)),
  resolve: {
    alias: { "/src": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy,
  },
  build: {
    outDir: fileURLToPath(new URL("./dist", import.meta.url)),
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL("./src/entry/index.html", import.meta.url)),
        admin: fileURLToPath(new URL("./src/entry/admin/index.html", import.meta.url)),
        login: fileURLToPath(new URL("./src/entry/login/index.html", import.meta.url)),
      },
    },
  },
});
