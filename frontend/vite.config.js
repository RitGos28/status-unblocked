import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// PORT moves the backend the dev proxy talks to, WEB_PORT this dev server.
const backend = `http://127.0.0.1:${process.env.PORT || 8000}`;

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.WEB_PORT) || 5173,
    proxy: {
      "/api": {
        target: backend,
        changeOrigin: true,
        secure: false,
      },
      "/healthz": {
        target: backend,
        changeOrigin: true,
      },
    },
  },
});
