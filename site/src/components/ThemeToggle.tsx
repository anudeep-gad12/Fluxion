import { useEffect, useState } from "react"
import { Moon, Sun } from "lucide-react"

type Theme = "light" | "dark"

function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light"
}

function applyTheme(theme: Theme) {
  if (theme === "dark") {
    document.documentElement.dataset.theme = "dark"
  } else {
    delete document.documentElement.dataset.theme
  }
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(currentTheme)

  // Until the user explicitly picks a theme, follow the OS preference live.
  useEffect(() => {
    let saved: string | null = null
    try {
      saved = localStorage.getItem("theme")
    } catch {
      /* ignore */
    }
    if (saved !== null) return

    const mq = window.matchMedia("(prefers-color-scheme: dark)")
    const onChange = () => {
      const next: Theme = mq.matches ? "dark" : "light"
      applyTheme(next)
      setTheme(next)
    }
    mq.addEventListener("change", onChange)
    return () => mq.removeEventListener("change", onChange)
  }, [])

  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark"
    applyTheme(next)
    try {
      localStorage.setItem("theme", next)
    } catch {
      /* ignore storage failures (private mode, etc.) */
    }
    setTheme(next)
  }

  const goingDark = theme === "light"

  return (
    <button
      type="button"
      className="themeToggle"
      onClick={toggle}
      aria-label={goingDark ? "Switch to dark theme" : "Switch to light theme"}
      title={goingDark ? "Dark theme" : "Light theme"}
    >
      {goingDark ? <Moon size={16} aria-hidden /> : <Sun size={16} aria-hidden />}
    </button>
  )
}
