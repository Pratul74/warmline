// Vite build settings: React, Tailwind, the "@/..." import alias, the site URL for link
// previews, and the test environment.
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// Writes the site's public address into index.html (the og:url and og:image tags), which
// must be absolute URLs. Falls back to the local dev address when VITE_SITE_URL is not set.
function siteUrlPlugin(siteUrl) {
  return {
    name: "warmline-site-url",
    transformIndexHtml: (html) => html.replaceAll("%SITE_URL%", siteUrl),
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd());
  const siteUrl = (env.VITE_SITE_URL || "http://localhost:5173").replace(/\/$/, "");

  return {
    plugins: [react(), tailwindcss(), siteUrlPlugin(siteUrl)],
    resolve: {
      // "@/components/ui/button" instead of "../../components/ui/button".
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: { port: 5173, strictPort: true },
    preview: { port: 4173, strictPort: true },
    test: { environment: "jsdom" },
  };
});
