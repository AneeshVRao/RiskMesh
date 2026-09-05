import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Client-only SPA hitting the FastAPI backend directly (it sends
// Access-Control-Allow-Origin: * -- see riskmesh/api/main.py -- so no dev
// proxy is needed; the browser talks straight to http://127.0.0.1:8000 the
// same way mockups/api.js does).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173 },
});
