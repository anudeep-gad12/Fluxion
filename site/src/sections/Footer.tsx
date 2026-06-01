import { Logo } from "../components/Logo"
import { DOWNLOAD_URL, GITHUB_URL } from "../constants"

export function Footer() {
  return (
    <footer>
      <div className="footerBrand">
        <Logo size={20} showWordmark={false} />
        <span>© 2026 Fluxion</span>
        <span>
          Built by <a href="https://anudeep.cc">Anudeep</a>
        </span>
      </div>
      <div className="footerLinks">
        <a href={GITHUB_URL} target="_blank" rel="noreferrer">
          GitHub
        </a>
        <a href={DOWNLOAD_URL}>Download</a>
        <a href="#capabilities">Features</a>
      </div>
    </footer>
  )
}
