import { useEffect, useRef } from "react"
import { Download } from "lucide-react"
import { InstallCommand } from "../components/InstallCommand"
import {
  APP_DEMO_VIDEO_MP4,
  APP_DEMO_VIDEO_HEIGHT,
  APP_DEMO_VIDEO_WIDTH,
  BREW_COMMAND,
  DOCS_URL,
  DOWNLOAD_URL,
} from "../constants"

export function HeroSection() {
  const videoRef = useRef<HTMLVideoElement | null>(null)

  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    video.muted = true
    video.playsInline = true
    void video.play().catch(() => {
      // Keep native controls visible if the browser blocks autoplay.
    })
  }, [])

  return (
    <section id="top" className="hero">
      <div className="heroInner container">
        <h1 id="hero-heading" className="heroTitle">
          Coding agent for the models you choose.
        </h1>
        <p className="heroLead">
          Plan, edit, grep, and run terminals — local models, APIs, or subscriptions you already pay for.
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
        <video
          ref={videoRef}
          className="heroMedia"
          width={APP_DEMO_VIDEO_WIDTH}
          height={APP_DEMO_VIDEO_HEIGHT}
          preload="auto"
          autoPlay
          muted
          loop
          playsInline
          disablePictureInPicture
          aria-label="Fluxion product demo"
        >
          <source src={APP_DEMO_VIDEO_MP4} type="video/mp4" />
        </video>
      </figure>
    </section>
  )
}
