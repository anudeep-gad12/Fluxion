import { BREW_COMMAND } from "../constants"
import { InstallCommand } from "./InstallCommand"

/** Grok-style install card before final CTA. */
export function InstallPreCta() {
  return (
    <section className="installPreCta container" aria-labelledby="install-pre-cta-heading">
      <div className="installPreCtaCard">
        <div className="installPreCtaCopy">
          <h2 id="install-pre-cta-heading">Try it on your Mac</h2>
          <p>One command to install. Works with any codebase, any language, right now.</p>
        </div>
        <InstallCommand command={BREW_COMMAND} className="installPreCtaCmd" />
      </div>
    </section>
  )
}
