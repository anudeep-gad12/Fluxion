import { Download } from "lucide-react"
import { DOWNLOAD_URL } from "../constants"

export function FinalCta() {
  return (
    <section className="finalCta">
      <div className="container finalCtaInner">
        <h2>Bring Fluxion to your Mac</h2>
        <p>Download the app, attach a workspace, and let the agent work — on your machine.</p>
        <a className="btn btnPrimary btnPrimary--hero" href={DOWNLOAD_URL}>
          <Download size={18} aria-hidden />
          Download for macOS
        </a>
      </div>
    </section>
  )
}
