import path from "path"
import { fileURLToPath } from "url"
import { copyFileSync, mkdirSync } from "fs"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

const projectRoot = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [
    react(),
    {
      name: "copy-favicon",
      closeBundle() {
        mkdirSync("dist/assets", { recursive: true })
        copyFileSync("public/favicon.svg", "dist/assets/favicon.svg")
      },
    },
  ],
  resolve: {
    alias: {
      "@": path.resolve(projectRoot, "./src"),
    },
  },
  server: {
    host: "127.0.0.1",
    port: 3000,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:9000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
