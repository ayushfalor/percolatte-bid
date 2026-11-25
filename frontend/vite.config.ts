import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In Docker, nginx serves the built files and forwards /api to the api container.
// For local development (npm run dev) Vite forwards the same paths to localhost:8000.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/docs": "http://localhost:8000",
      "/openapi.json": "http://localhost:8000",
    },
  },
});
