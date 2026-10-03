import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the UI runs on :5173 and proxies API calls to companion-api on :8710.
// In production the API serves the built files from apps/desk/dist.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/v1": { target: "http://127.0.0.1:8710", changeOrigin: false },
      "/healthz": "http://127.0.0.1:8710",
      "/readyz": "http://127.0.0.1:8710",
      "/version": "http://127.0.0.1:8710"
    }
  },
  build: { outDir: "dist", sourcemap: false, target: "es2020" }
});
