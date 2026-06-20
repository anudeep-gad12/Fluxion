import { useEffect, useRef, useState, type KeyboardEvent } from "react"
import { Check, Monitor, Moon, Sun, type LucideIcon } from "lucide-react"

type Theme = "light" | "dark"
type ThemePreference = Theme | "system"

const OPTIONS: Array<{ value: ThemePreference; label: string; icon: LucideIcon }> = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
]

function savedPreference(): ThemePreference {
  try {
    const value = localStorage.getItem("theme")
    return value === "light" || value === "dark" || value === "system" ? value : "system"
  } catch {
    return "system"
  }
}

function systemTheme(): Theme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
}

function applyTheme(theme: Theme) {
  if (theme === "dark") document.documentElement.dataset.theme = "dark"
  else delete document.documentElement.dataset.theme
  document.documentElement.style.colorScheme = theme
  document
    .querySelector<HTMLMetaElement>('meta[name="theme-color"]')
    ?.setAttribute("content", theme === "light" ? "#f7f7f4" : "#000000")
}

export function ThemeToggle() {
  const [preference, setPreference] = useState<ThemePreference>(savedPreference)
  const [resolvedSystemTheme, setResolvedSystemTheme] = useState<Theme>(systemTheme)
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([])
  const activeIndex = OPTIONS.findIndex((option) => option.value === preference)
  const TriggerIcon = OPTIONS[activeIndex]?.icon ?? Monitor
  const theme = preference === "system" ? resolvedSystemTheme : preference

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)")
    const handleChange = () => setResolvedSystemTheme(media.matches ? "dark" : "light")
    handleChange()
    media.addEventListener("change", handleChange)
    return () => media.removeEventListener("change", handleChange)
  }, [])

  useEffect(() => {
    if (!open) return
    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const handleEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return
      setOpen(false)
      triggerRef.current?.focus()
    }
    document.addEventListener("mousedown", handlePointerDown)
    document.addEventListener("keydown", handleEscape)
    requestAnimationFrame(() => optionRefs.current[activeIndex]?.focus())
    return () => {
      document.removeEventListener("mousedown", handlePointerDown)
      document.removeEventListener("keydown", handleEscape)
    }
  }, [activeIndex, open])

  const selectPreference = (nextPreference: ThemePreference) => {
    try {
      localStorage.setItem("theme", nextPreference)
    } catch {
      /* Keep the in-memory choice when storage is unavailable. */
    }
    setPreference(nextPreference)
    setOpen(false)
    triggerRef.current?.focus()
  }

  const handleMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const currentIndex = optionRefs.current.findIndex((option) => option === document.activeElement)
    let nextIndex: number | null = null
    if (event.key === "ArrowDown") nextIndex = (currentIndex + 1 + OPTIONS.length) % OPTIONS.length
    if (event.key === "ArrowUp") nextIndex = (currentIndex - 1 + OPTIONS.length) % OPTIONS.length
    if (event.key === "Home") nextIndex = 0
    if (event.key === "End") nextIndex = OPTIONS.length - 1
    if (nextIndex === null) return
    event.preventDefault()
    optionRefs.current[nextIndex]?.focus()
  }

  return (
    <div ref={rootRef} className="themeMenuRoot">
      <button
        ref={triggerRef}
        type="button"
        className="themeToggle"
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return
          event.preventDefault()
          setOpen(true)
        }}
        aria-label={`Theme: ${OPTIONS[activeIndex]?.label ?? "System"}`}
        aria-haspopup="menu"
        aria-expanded={open}
        title="Theme"
      >
        <TriggerIcon size={16} aria-hidden />
      </button>
      {open ? (
        <div className="themeMenu" role="menu" aria-label="Theme" onKeyDown={handleMenuKeyDown}>
          {OPTIONS.map((option, index) => {
            const Icon = option.icon
            const selected = option.value === preference
            return (
              <button
                key={option.value}
                ref={(node) => { optionRefs.current[index] = node }}
                type="button"
                role="menuitemradio"
                aria-checked={selected}
                tabIndex={selected ? 0 : -1}
                className="themeMenuOption"
                data-selected={selected ? "true" : "false"}
                onClick={() => selectPreference(option.value)}
              >
                <Icon size={16} aria-hidden />
                <span>{option.label}</span>
                <Check className="themeMenuCheck" size={14} aria-hidden />
              </button>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}
