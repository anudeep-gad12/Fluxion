import React, { useState } from "react"
import ReactDOM from "react-dom/client"
import { Box, Check, Code2, Copy, Database, Download, Github, Laptop, Sparkles, Terminal } from "lucide-react"
import { HeroIllustration } from "./components/HeroIllustration"
import { Logo } from "./components/Logo"
import "./styles.css"

const GITHUB_URL = "https://github.com/anudeep-gad12/Fluxion"
const DOWNLOAD_URL = "https://github.com/anudeep-gad12/Fluxion/releases/latest/download/Fluxion-macos-arm64.dmg"
const BREW_COMMAND = "brew install --cask anudeep-gad12/tap/fluxion"

function Header() {
  return (
    <header className="nav">
      <a className="logo" href="#top" aria-label="Fluxion home">
        <Logo size={28} />
      </a>
      <nav>
        <a href="#features">Features</a>
        <a className="navStar" href={GITHUB_URL}>
          <Github size={14} aria-hidden />
          Star
        </a>
        <a className="navCta" href={DOWNLOAD_URL}>Download</a>
      </nav>
    </header>
  )
}

function BrewInstallPill() {
  const [copied, setCopied] = useState(false)

  const copyInstall = async () => {
    await navigator.clipboard.writeText(BREW_COMMAND)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1300)
  }

  return (
    <div className="brewLine">
      <span>or install with Homebrew</span>
      <button type="button" className="brewCommand" onClick={copyInstall} aria-label="Copy Homebrew install command">
        <code>{BREW_COMMAND}</code>
        {copied ? <Check size={15} /> : <Copy size={15} />}
      </button>
    </div>
  )
}

function Hero() {
  return (
    <section id="top" className="hero section">
      <div className="eyebrow"><Sparkles size={14} /> fluxion.cc</div>
      <h1>A local coding agent for the models you choose.</h1>
      <p className="heroCopy">
        Fluxion is a native macOS app: pick hosted or local models, attach a repo workspace,
        and let the agent read files, edit code, run shell commands, and search the web — with
        conversations stored on your machine.
      </p>
      <div className="actions heroActions">
        <a className="primary" href={DOWNLOAD_URL}><Download size={18} /> Download for macOS</a>
      </div>
      <BrewInstallPill />
      <div className="heroStage">
        <div className="illustrationFrame">
          <HeroIllustration />
        </div>
      </div>
    </section>
  )
}

const cards = [
  { icon: Laptop, title: "Bring your own model", body: "Use local GGUF/MLX models or provider APIs from OpenRouter, DeepInfra, and Fireworks." },
  { icon: Code2, title: "Works inside your repo", body: "Point Fluxion at a workspace and let the agent read files, edit code, run bash, and verify changes." },
  { icon: Terminal, title: "Integrated terminal", body: "Open multiple PTY sessions per conversation — run tests, servers, and git next to the agent thread." },
  { icon: Database, title: "Conversations stay local", body: "SQLite storage lives in Application Support. App updates preserve conversations, settings, and keys." },
  { icon: Box, title: "Open source, forkable", body: "FastAPI, React, Tauri, SQLite, Apache-2.0. Change the parts you do not like." },
]

function FeatureCard({ icon: Icon, title, body }: (typeof cards)[number]) {
  return (
    <article className="infoCard">
      <Icon size={20} />
      <h3>{title}</h3>
      <p>{body}</p>
    </article>
  )
}

function FeatureCards() {
  return (
    <section id="features" className="section featureSection">
      <div className="sectionIntro">
        <span className="label">features</span>
        <h2>One app for models, repo work, and terminals.</h2>
        <p>Everything runs locally on your Mac — no browser tab juggling.</p>
      </div>
      <div className="cardsGrid">
        <div className="cardsRow">
          {cards.slice(0, 3).map((card) => (
            <FeatureCard key={card.title} {...card} />
          ))}
        </div>
        <div className="cardsRow cardsRowBottom">
          {cards.slice(3).map((card) => (
            <FeatureCard key={card.title} {...card} />
          ))}
        </div>
      </div>
    </section>
  )
}

function FinalCta() {
  return (
    <section className="section finalCta">
      <h2>Give your local models a coding agent.</h2>
      <p>Install Fluxion, pick a model, attach a repo, and let it work.</p>
      <div className="actions">
        <a className="primary" href={DOWNLOAD_URL}><Download size={18} /> Download for macOS</a>
      </div>
      <BrewInstallPill />
    </section>
  )
}

function App() {
  return (
    <main>
      <Header />
      <Hero />
      <FeatureCards />
      <FinalCta />
      <footer>
        <div className="footerBrand">
          <Logo size={24} showWordmark={false} className="footerLogo" />
          <span>© 2026 Fluxion · Apache-2.0</span>
          <span>Built by <a href="https://anudeep.cc">Anudeep</a></span>
        </div>
        <div className="footerLinks">
          <a href={GITHUB_URL}>GitHub</a>
          <a href={DOWNLOAD_URL}>Download</a>
        </div>
      </footer>
    </main>
  )
}

ReactDOM.createRoot(document.getElementById("root")!).render(<App />)
