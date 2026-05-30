export function AgentWorkIllustration() {
  return (
    <svg
      className="productIllustration"
      viewBox="0 0 640 420"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Fluxion agent working in a repo"
    >
      <rect width="640" height="420" rx="16" fill="#0c0c0e" stroke="rgba(255,255,255,0.08)" />
      <text x="28" y="40" fontFamily="system-ui,sans-serif" fontSize="12" fill="#71717a">
        Agent · my-app
      </text>

      <circle cx="40" cy="72" r="5" fill="#79e6ff" />
      <line x1="40" y1="77" x2="40" y2="120" stroke="rgba(121,230,255,0.3)" strokeWidth="2" />
      <rect x="56" y="58" width="556" height="48" rx="10" fill="#141416" />
      <text x="72" y="80" fontFamily="system-ui,sans-serif" fontSize="11" fill="#71717a">
        read_file
      </text>
      <text x="72" y="98" fontFamily="ui-monospace,monospace" fontSize="11" fill="#a1a1aa">
        orchestrator/auth/middleware.py
      </text>

      <circle cx="40" cy="140" r="5" fill="#79e6ff" />
      <line x1="40" y1="145" x2="40" y2="220" stroke="rgba(121,230,255,0.3)" strokeWidth="2" />
      <rect x="56" y="126" width="556" height="80" rx="10" fill="#141416" />
      <text x="72" y="148" fontFamily="system-ui,sans-serif" fontSize="11" fill="#71717a">
        edit_file
      </text>
      <rect x="72" y="158" width="520" height="10" rx="3" fill="rgba(74,222,128,0.35)" />
      <rect x="72" y="174" width="400" height="10" rx="3" fill="rgba(239,68,68,0.28)" />
      <rect x="72" y="190" width="460" height="10" rx="3" fill="rgba(74,222,128,0.22)" />

      <circle cx="40" cy="240" r="5" fill="#79e6ff" />
      <rect x="56" y="226" width="556" height="48" rx="10" fill="#141416" />
      <text x="72" y="248" fontFamily="system-ui,sans-serif" fontSize="11" fill="#71717a">
        bash
      </text>
      <text x="72" y="266" fontFamily="ui-monospace,monospace" fontSize="11" fill="#a1a1aa">
        uv run pytest tests/auth -q
      </text>

      <rect x="28" y="300" width="584" height="56" rx="12" fill="#141416" stroke="rgba(255,255,255,0.06)" />
      <text x="44" y="334" fontFamily="system-ui,sans-serif" fontSize="13" fill="#d4d4d8">
        Middleware fixed — auth tests pass.
      </text>

      <rect x="28" y="372" width="584" height="32" rx="8" fill="rgba(74,222,128,0.08)" stroke="rgba(74,222,128,0.2)" />
      <text x="44" y="393" fontFamily="system-ui,sans-serif" fontSize="12" fill="#4ade80">
        ✓ 10 passed · run complete
      </text>
    </svg>
  );
}
