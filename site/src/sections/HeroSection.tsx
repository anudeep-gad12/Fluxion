import { Download } from "lucide-react"
import { InstallCommand } from "../components/InstallCommand"
import {
  APP_SCREENSHOT_HEIGHT,
  APP_SCREENSHOT_PNG,
  APP_SCREENSHOT_WEBP,
  APP_SCREENSHOT_WIDTH,
  BREW_COMMAND,
  DOCS_URL,
  DOWNLOAD_URL,
} from "../constants"

export function HeroSection() {
  return (
    <section id="top" className="hero">
      <div className="heroInner container">
        <h1 id="hero-heading" className="heroTitle">
          The native coding agent for your Mac.
        </h1>
        <p className="heroLead">
          Plan, edit, grep, and run terminals — local models or the APIs you already pay for.
        </p>
        <div className="heroActions">
          <a className="btn btnPrimary btnPrimary--hero" href={DOWNLOAD_URL}>
            <Download size={18} aria-hidden />
            Download for macOS
          </a>
        </div>
        <div className="heroFoot">
          <InstallCommand command={BREW_COMMAND} className="installCmd--hero" label="Or install with Homebrew" />
          <p className="heroNote">
            Open source · <a href={DOWNLOAD_URL}>DMG</a>
            {" · "}
            <a href={DOCS_URL} target="_blank" rel="noreferrer">
              Docs
            </a>
          </p>
        </div>
      </div>

      <figure className="heroShot container">
        <picture>
          <source srcSet={APP_SCREENSHOT_WEBP} type="image/webp" />
          <img
            src={APP_SCREENSHOT_PNG}
            alt="Fluxion on macOS"
            width={APP_SCREENSHOT_WIDTH}
            height={APP_SCREENSHOT_HEIGHT}
            sizes="(min-width: 1180px) 1180px, calc(100vw - 48px)"
            loading="eager"
            decoding="async"
            fetchPriority="high"
          />
        </picture>
      </figure>
    </section>
  )
}
