import { useState } from "react"
import { Check, Copy } from "lucide-react"

interface InstallCommandProps {
  command: string
  label?: string
  className?: string
}

/** Prominent copyable install line — x.ai/cli style. */
export function InstallCommand({ command, label, className = "" }: InstallCommandProps) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    await navigator.clipboard.writeText(command)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1300)
  }

  return (
    <div className={`installCmd ${className}`.trim()}>
      {label && <span className="installCmdLabel">{label}</span>}
      <button type="button" className="installCmdInner" onClick={copy} aria-label="Copy install command">
        <span className="installCmdPrompt">$</span>
        <code>{command}</code>
        <span className="installCmdIcon" aria-hidden>
          {copied ? <Check size={16} /> : <Copy size={16} />}
        </span>
      </button>
    </div>
  )
}
