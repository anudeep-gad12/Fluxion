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

    const interactionEvents = ["pointerdown", "touchstart", "keydown", "scroll", "mousemove"] as const
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) tryPlay()
      },
      { threshold: 0.25 },
    )

    const cleanup = () => {
      video.removeEventListener("loadeddata", tryPlay)
      video.removeEventListener("canplay", tryPlay)
      interactionEvents.forEach((evt) => window.removeEventListener(evt, tryPlay))
      observer.disconnect()
    }

    function tryPlay() {
      const attempt = video!.play()
      if (attempt && typeof attempt.then === "function") {
        attempt
          .then(cleanup) // playing — drop all fallback listeners
          .catch(() => {
            // Autoplay blocked (e.g. Safari "Never Auto-Play", Low Power Mode).
            // Listeners below retry on data ready / first interaction / visibility.
          })
      }
    }

    tryPlay()
    video.addEventListener("loadeddata", tryPlay)
    video.addEventListener("canplay", tryPlay)
    interactionEvents.forEach((evt) => window.addEventListener(evt, tryPlay, { passive: true }))
    observer.observe(video)

    return cleanup
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
