import React, { useState } from "react"
import ReactDOM from "react-dom/client"
import { ArrowUpRight, Box, Check, Code2, Copy, Database, Download, Github, Laptop, Sparkles } from "lucide-react"
import "./styles.css"

const GITHUB_URL = "https://github.com/anudeep-gad12/Fluxion"
const DOWNLOAD_URL = "https://github.com/anudeep-gad12/Fluxion/releases/latest/download/Fluxion-macos-arm64.zip"
const BREW_COMMAND = "brew install --cask anudeep-gad12/tap/fluxion"
const INSTALL_COMMANDS = `${BREW_COMMAND}
open /Applications/Fluxion.app`

type ShotProps = {
  src: string
  label: string
  kicker?: string
  tall?: boolean
}

function ScreenshotSlot({ src, label, kicker, tall = false }: ShotProps) {
  const [loaded, setLoaded] = useState(false)

  return (
    <div className={`shot ${tall ? "shotTall" : ""}`}>
      <img
        className={loaded ? "isLoaded" : ""}
        src={src}
        alt=""
        aria-hidden="true"
        onLoad={() => setLoaded(true)}
        onError={() => setLoaded(false)}
      />
      <div className={`shotPlaceholder ${loaded ? "isHidden" : ""}`}>
        <div className="placeholderIcon"><Sparkles size={18} /></div>
        {kicker ? <span>{kicker}</span> : null}
        <strong>{label}</strong>
        <small>{src}</small>
      </div>
    </div>
  )
}

function Header() {
  return (
    <header className="nav">
      <a className="logo" href="#top" aria-label="Fluxion home"><span>~&gt;</span>Fluxion</a>
      <nav>
        <a href="#models">Models</a>
        <a href="#local">Local</a>
        <a href={GITHUB_URL}>GitHub</a>
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
        Fluxion runs on your Mac, works inside your repo, reads files, edits code,
        runs shell commands, searches the web, and keeps the conversation going.
      </p>
      <div className="actions">
        <a className="primary" href={DOWNLOAD_URL}><Download size={18} /> Download for macOS</a>
        <a className="secondary" href={GITHUB_URL}><Github size={18} /> Star on GitHub</a>
      </div>
      <BrewInstallPill />
      <div className="heroStage">
        <ScreenshotSlot src="/images/hero-app.png" label="Fluxion workspace run screenshot" kicker="product image" />
      </div>
    </section>
  )
}

const cards = [
  { icon: Laptop, title: "Bring your own model", body: "Use local GGUF/MLX models or provider APIs from OpenRouter, DeepInfra, and Fireworks." },
  { icon: Code2, title: "Works inside your repo", body: "Point Fluxion at a workspace and let the agent read files, edit code, run bash, and verify changes." },
  { icon: Database, title: "Conversations stay local", body: "SQLite storage lives in Application Support. App updates preserve conversations, settings, and keys." },
  { icon: Box, title: "Open source, forkable", body: "FastAPI, React, SQLite, Apache-2.0. Change the parts you do not like." },
]

function FeatureCards() {
  return (
    <section className="section cardsGrid">
      {cards.map(({ icon: Icon, title, body }) => (
        <article className="infoCard" key={title}>
          <Icon size={20} />
          <h3>{title}</h3>
          <p>{body}</p>
        </article>
      ))}
    </section>
  )
}

function SplitSection() {
  return (
    <section id="models" className="section split">
      <div>
        <span className="label">model freedom</span>
        <h2>Local when you want it. Hosted when you need it.</h2>
        <p>
          Fluxion does not lock the agent to one provider. Pick a local model from
          your machine, switch to a hosted model for heavier work, and keep the same thread.
        </p>
        <ul>
          <li>Local GGUF and MLX model discovery</li>
          <li>Provider keys saved in local settings</li>
          <li>Per-thread model switching from the app</li>
        </ul>
      </div>
      <ScreenshotSlot src="/images/model-picker.png" label="Fluxion model picker screenshot" />
    </section>
  )
}

function WorkSection() {
  return (
    <section className="section workGrid textOnly">
      <div className="workCopy">
        <span className="label">repo work</span>
        <h2>Watch it work through the codebase.</h2>
        <p>
          The agent can inspect your codebase, edit files, run commands, search the web,
          extract pages, and return with a verified change instead of a vague suggestion.
        </p>
      </div>
    </section>
  )
}

function LocalSection() {
  return (
    <section id="local" className="section localText">
      <span className="label">local app</span>
      <h2>Your chats, settings, and workspace context stay on your machine.</h2>
      <p>
        The macOS package starts a localhost service, opens the browser UI, and stores
        conversations outside the app bundle so updates do not wipe your history.
      </p>
      <ul>
        <li>Unsigned macOS app package</li>
        <li>Persistent SQLite conversations</li>
        <li>Open-source fallback from source</li>
      </ul>
    </section>
  )
}

function TerminalBlock() {
  const [copied, setCopied] = useState(false)

  const copyInstall = async () => {
    await navigator.clipboard.writeText(INSTALL_COMMANDS)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1300)
  }

  return (
    <section className="section terminalSection">
      <div className="terminalWindow">
        <div className="terminalTop">
          <i /><i /><i />
          <span>~/fluxion</span>
          <button type="button" onClick={copyInstall}>{copied ? "Copied" : "Copy"}</button>
        </div>
        <pre>{`$ ${INSTALL_COMMANDS.split("\n").join("\n$ ")}
✓ local service running at http://127.0.0.1:9000`}</pre>
      </div>
      <div>
        <span className="label">install</span>
        <h2>Install with Homebrew, open Fluxion.</h2>
        <p>
          Homebrew downloads the release zip, installs Fluxion.app into Applications,
          and keeps upgrades simple. Manual zip install stays available from GitHub.
        </p>
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
        <a className="secondary" href={GITHUB_URL}>View source <ArrowUpRight size={17} /></a>
      </div>
    </section>
  )
}

function App() {
  return (
    <main>
      <Header />
      <Hero />
      <FeatureCards />
      <SplitSection />
      <WorkSection />
      <LocalSection />
      <TerminalBlock />
      <FinalCta />
      <footer>
        <div className="footerBrand">
          <span className="logoMark">~&gt;</span>
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
