import path from "path"
import { fileURLToPath } from "url"
import { copyFileSync, mkdirSync, writeFileSync } from "fs"
import react from "@vitejs/plugin-react"
import { defineConfig, type Plugin } from "vite"

const projectRoot = path.dirname(fileURLToPath(import.meta.url))
const uiBuildAt = new Date().toISOString()

function uiBuildStampPlugin(buildAt: string): Plugin {
  return {
    name: "ui-build-stamp",
    closeBundle() {
      mkdirSync("dist/assets", { recursive: true })
      copyFileSync("public/favicon.svg", "dist/assets/favicon.svg")
      writeFileSync(
        "dist/ui-build.json",
        JSON.stringify({ builtAt: buildAt }, null, 2)
      )
    },
  }
}

export default defineConfig({
  define: {
    __UI_BUILD_AT__: JSON.stringify(uiBuildAt),
  },
  plugins: [react(), uiBuildStampPlugin(uiBuildAt)],
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
