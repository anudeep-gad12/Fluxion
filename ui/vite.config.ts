import path from "path"
import { copyFileSync, mkdirSync } from "fs"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

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
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:9000",
        changeOrigin: true,
      },
    },
  },
})
