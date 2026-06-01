import { useEffect, useState } from "react"
import { Github } from "lucide-react"
import { Logo } from "../components/Logo"
import { DOCS_URL, DOWNLOAD_URL, GITHUB_URL } from "../constants"

export function Header() {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12)
    onScroll()
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  return (
    <header className={`nav nav--fixed ${scrolled ? "nav--scrolled" : ""}`.trim()}>
      <div className="navInner">
        <a className="logo" href="#top" aria-label="Fluxion home">
          <Logo size={24} />
        </a>
        <nav className="navLinks" aria-label="Primary">
          <a href="#capabilities">Features</a>
          <a href={DOCS_URL} target="_blank" rel="noreferrer">
            Docs
          </a>
          <a className="navStar" href={GITHUB_URL} target="_blank" rel="noreferrer">
            <Github size={15} aria-hidden />
            Star
          </a>
          <a className="navCta" href={DOWNLOAD_URL}>
            Download
          </a>
        </nav>
      </div>
    </header>
  )
}
