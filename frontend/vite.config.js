import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The browser calls the API directly at VITE_API_BASE_URL (see .env.example).
// The backend allows this page's origin through CORS (CORS_ALLOWED_ORIGINS).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
  },
  test: {
    environment: "jsdom",
  },
});
