import {
  Brain,
  FolderGit2,
  GitBranch,
  Globe,
  KeyRound,
  Laptop,
  ListChecks,
  Search,
  Shield,
  Sparkles,
  SquareTerminal,
  Terminal,
  Wrench,
} from "lucide-react"
import type { LucideIcon } from "lucide-react"

type Capability = {
  icon: LucideIcon
  title: string
  description: string
}

const CAPABILITIES: Capability[] = [
  {
    icon: ListChecks,
    title: "Plan mode",
    description: "Propose a structured approach before writing code.",
  },
  {
    icon: Wrench,
    title: "Agent tool loop",
    description: "Read, edit, grep, bash, and web search in one thread.",
  },
  {
    icon: Terminal,
    title: "Integrated terminals",
    description: "Multiple PTY tabs per conversation.",
  },
  {
    icon: Brain,
    title: "Thinking traces",
    description: "Follow step-by-step reasoning on supported models.",
  },
  {
    icon: FolderGit2,
    title: "Repo workspaces",
    description: "Point Fluxion at any project folder on your Mac.",
  },
  {
    icon: Sparkles,
    title: "Multi-file edits",
    description: "Apply diffs across files with visible agent steps.",
  },
  {
    icon: Search,
    title: "Code search",
    description: "Grep and navigate large trees from the agent.",
  },
  {
    icon: GitBranch,
    title: "Git in the shell",
    description: "Stage, commit, and branch beside the agent thread.",
  },
  {
    icon: Globe,
    title: "Web search",
    description: "Look up docs and packages when the agent needs them.",
  },
  {
    icon: SquareTerminal,
    title: "In-app browser",
    description: "Open links in Fluxion browser tabs, not Safari.",
  },
  {
    icon: Laptop,
    title: "SQLite on disk",
    description: "Chats and settings live in Application Support.",
  },
  {
    icon: KeyRound,
    title: "macOS keychain",
    description: "API keys stored in the system keychain.",
  },
  {
    icon: Laptop,
    title: "Native macOS app",
    description: "Tauri shell — fast, local, and desktop-native.",
  },
  {
    icon: Shield,
    title: "Open source",
    description: "Apache-2.0 — fork and change what you want.",
  },
  {
    icon: Shield,
    title: "Tool approvals",
    description: "Strict, relaxed, or YOLO policies for agent tools.",
  },
]

export function CapabilityGrid() {
  return (
    <section id="capabilities" className="capabilitySection container" aria-labelledby="capabilities-heading">
      <header className="capabilityHeader">
        <h2 id="capabilities-heading">Built for the full loop on your Mac</h2>
        <p>Plan, agent, terminal, and browser — without leaving the workspace.</p>
      </header>
      <ul className="capabilityGrid">
        {CAPABILITIES.map((item) => {
          const Icon = item.icon
          return (
            <li key={item.title} className="capabilityItem">
              <Icon className="capabilityIcon" size={20} aria-hidden />
              <div className="capabilityText">
                <h3>{item.title}</h3>
                <p>{item.description}</p>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
