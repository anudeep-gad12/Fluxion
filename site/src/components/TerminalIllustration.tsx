export function TerminalIllustration() {
  return (
    <svg
      className="productIllustration"
      viewBox="0 0 640 420"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Fluxion integrated terminal"
    >
      <rect width="640" height="420" rx="16" fill="#09090b" stroke="rgba(255,255,255,0.08)" />
      <rect x="0" y="0" width="640" height="48" fill="#0c0c0e" rx="16" />
      <text x="24" y="30" fontFamily="system-ui,sans-serif" fontSize="12" fill="#71717a">
        Terminal
      </text>
      <rect x="24" y="60" width="96" height="26" rx="6" fill="rgba(121,230,255,0.12)" />
      <text x="36" y="77" fontFamily="ui-monospace,monospace" fontSize="11" fill="#79e6ff">
        zsh · 1
      </text>
      <rect x="128" y="60" width="80" height="26" rx="6" fill="rgba(255,255,255,0.04)" />
      <text x="140" y="77" fontFamily="ui-monospace,monospace" fontSize="11" fill="#52525b">
        zsh · 2
      </text>
      <text x="600" y="77" fontFamily="system-ui,sans-serif" fontSize="18" fill="#52525b" textAnchor="end">
        +
      </text>
      <rect x="24" y="100" width="592" height="296" rx="10" fill="#050608" stroke="rgba(255,255,255,0.05)" />
      <text x="40" y="132" fontFamily="ui-monospace,monospace" fontSize="12" fill="#4ade80">
        ~/Projects/my-app
      </text>
      <text x="40" y="158" fontFamily="ui-monospace,monospace" fontSize="12" fill="#a1a1aa">
        $ git status -sb
      </text>
      <text x="40" y="184" fontFamily="ui-monospace,monospace" fontSize="12" fill="#71717a">
        ## main...origin/main
      </text>
      <text x="40" y="210" fontFamily="ui-monospace,monospace" fontSize="12" fill="#71717a">
        M  orchestrator/auth.py
      </text>
      <text x="40" y="244" fontFamily="ui-monospace,monospace" fontSize="12" fill="#a1a1aa">
        $ uv run pytest -q
      </text>
      <text x="40" y="270" fontFamily="ui-monospace,monospace" fontSize="12" fill="#4ade80">
        10 passed in 2.1s
      </text>
      <text x="40" y="304" fontFamily="ui-monospace,monospace" fontSize="12" fill="#79e6ff">
        $
      </text>
    </svg>
  );
}
