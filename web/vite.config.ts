import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// VITE_BASE sets the path the desk is served under, for example /InventIQ/ on GitHub Pages.
export default defineConfig({
  base: process.env.VITE_BASE ?? "/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000", "/docs": "http://127.0.0.1:8000", "/openapi.json": "http://127.0.0.1:8000" },
  },
  build: { outDir: "dist", sourcemap: false },
});
