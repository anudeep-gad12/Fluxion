/** Inline product illustration — always renders, no external asset fetch. */
export function HeroIllustration() {
  return (
    <svg
      className="heroIllustration"
      viewBox="0 0 1200 680"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Fluxion desktop app with sidebar, agent thread, and terminal panel"
    >
      <defs>
        <linearGradient id="hi-bg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#111114" />
          <stop offset="1" stopColor="#09090b" />
        </linearGradient>
        <linearGradient id="hi-glow" x1="0.5" y1="0" x2="0.5" y2="1">
          <stop offset="0" stopColor="rgba(121,230,255,0.14)" />
          <stop offset="1" stopColor="rgba(121,230,255,0)" />
        </linearGradient>
        <filter id="hi-shadow" x="-8%" y="-8%" width="116%" height="120%">
          <feDropShadow dx="0" dy="18" stdDeviation="28" floodColor="#000" floodOpacity="0.55" />
        </filter>
      </defs>

      {/* backdrop glow */}
      <ellipse cx="600" cy="120" rx="420" ry="80" fill="url(#hi-glow)" />

      {/* window shell */}
      <rect x="24" y="24" width="1152" height="632" rx="18" fill="url(#hi-bg)" stroke="rgba(255,255,255,0.09)" filter="url(#hi-shadow)" />

      {/* titlebar */}
      <rect x="24" y="24" width="1152" height="36" rx="18" fill="#0c0c0e" />
      <rect x="24" y="44" width="1152" height="16" fill="#0c0c0e" />
      <circle cx="52" cy="42" r="6" fill="#ff5f57" />
      <circle cx="72" cy="42" r="6" fill="#febc2e" />
      <circle cx="92" cy="42" r="6" fill="#28c840" />

      {/* sidebar */}
      <rect x="24" y="60" width="208" height="596" fill="#09090b" />
      <line x1="232" y1="60" x2="232" y2="656" stroke="rgba(255,255,255,0.06)" />

      {/* brand */}
      <rect x="48" y="84" width="32" height="32" rx="7" fill="#141416" stroke="rgba(255,255,255,0.1)" />
      <text x="64" y="105" fontFamily="ui-monospace,monospace" fontSize="13" fontWeight="700" fill="#f4f4f5" textAnchor="middle">
        ~&gt;
      </text>
      <text x="88" y="105" fontFamily="system-ui,sans-serif" fontSize="14" fontWeight="600" fill="#f4f4f5">
        Fluxion
      </text>

      <text x="48" y="140" fontFamily="system-ui,sans-serif" fontSize="10" fontWeight="600" fill="#52525b" letterSpacing="0.1em">
        WORKSPACES
      </text>
      <rect x="40" y="152" width="176" height="30" rx="8" fill="rgba(121,230,255,0.1)" stroke="rgba(121,230,255,0.22)" />
      <text x="52" y="172" fontFamily="system-ui,sans-serif" fontSize="12" fill="#79e6ff">
        my-app
      </text>
      <text x="52" y="200" fontFamily="system-ui,sans-serif" fontSize="12" fill="#71717a">
        docs-site
      </text>
      <text x="52" y="224" fontFamily="system-ui,sans-serif" fontSize="12" fill="#71717a">
        api-sandbox
      </text>

      {/* main chat column */}
      <rect x="232" y="60" width="688" height="596" fill="#0c0c0e" />

      {/* user bubble */}
      <rect x="256" y="88" width="520" height="44" rx="12" fill="#141416" stroke="rgba(255,255,255,0.06)" />
      <text x="272" y="115" fontFamily="system-ui,sans-serif" fontSize="13" fill="#e4e4e7">
        Fix the auth middleware tests and run pytest
      </text>

      {/* agent step — grep */}
      <circle cx="268" cy="168" r="5" fill="#79e6ff" />
      <line x1="268" y1="173" x2="268" y2="228" stroke="rgba(121,230,255,0.25)" strokeWidth="2" />
      <rect x="284" y="152" width="580" height="56" rx="10" fill="#141416" stroke="rgba(255,255,255,0.05)" />
      <text x="300" y="174" fontFamily="system-ui,sans-serif" fontSize="11" fill="#71717a">
        grep
      </text>
      <text x="300" y="194" fontFamily="ui-monospace,monospace" fontSize="11" fill="#a1a1aa">
        grep -r &quot;session&quot; orchestrator/
      </text>

      {/* agent step — edit diff */}
      <circle cx="268" cy="248" r="5" fill="#79e6ff" />
      <line x1="268" y1="253" x2="268" y2="340" stroke="rgba(121,230,255,0.25)" strokeWidth="2" />
      <rect x="284" y="232" width="580" height="96" rx="10" fill="#141416" stroke="rgba(255,255,255,0.05)" />
      <text x="300" y="254" fontFamily="system-ui,sans-serif" fontSize="11" fill="#71717a">
        edit_file · auth.py
      </text>
      <rect x="300" y="266" width="540" height="10" rx="3" fill="rgba(74,222,128,0.35)" />
      <rect x="300" y="282" width="420" height="10" rx="3" fill="rgba(239,68,68,0.28)" />
      <rect x="300" y="298" width="480" height="10" rx="3" fill="rgba(74,222,128,0.22)" />

      {/* agent reply */}
      <rect x="284" y="348" width="580" height="52" rx="10" fill="transparent" />
      <text x="300" y="372" fontFamily="system-ui,sans-serif" fontSize="13" fill="#d4d4d8">
        Updated middleware — 10 tests passing.
      </text>

      {/* composer */}
      <rect x="256" y="560" width="640" height="72" rx="14" fill="#141416" stroke="rgba(255,255,255,0.08)" />
      <text x="276" y="592" fontFamily="system-ui,sans-serif" fontSize="12" fill="#52525b">
        Ask the agent…
      </text>
      <text x="276" y="616" fontFamily="system-ui,sans-serif" fontSize="11" fill="#71717a">
        Qwen3-32B · Agent
      </text>
      <circle cx="872" cy="596" r="16" fill="#e4e4e7" />

      {/* terminal rail */}
      <rect x="920" y="60" width="256" height="596" fill="#09090b" />
      <line x1="920" y1="60" x2="920" y2="656" stroke="rgba(255,255,255,0.06)" />
      <text x="944" y="88" fontFamily="system-ui,sans-serif" fontSize="11" fill="#71717a">
        Terminal
      </text>
      <rect x="944" y="98" width="108" height="22" rx="6" fill="rgba(121,230,255,0.12)" />
      <text x="956" y="113" fontFamily="ui-monospace,monospace" fontSize="10" fill="#79e6ff">
        zsh · 1
      </text>
      <rect x="1060" y="98" width="72" height="22" rx="6" fill="rgba(255,255,255,0.04)" />
      <text x="1072" y="113" fontFamily="ui-monospace,monospace" fontSize="10" fill="#52525b">
        zsh · 2
      </text>
      <rect x="944" y="132" width="208" height="488" rx="10" fill="#050608" stroke="rgba(255,255,255,0.05)" />
      <text x="960" y="160" fontFamily="ui-monospace,monospace" fontSize="11" fill="#4ade80">
        ~/Projects/my-app
      </text>
      <text x="960" y="182" fontFamily="ui-monospace,monospace" fontSize="11" fill="#a1a1aa">
        $ uv run pytest -q
      </text>
      <text x="960" y="204" fontFamily="ui-monospace,monospace" fontSize="11" fill="#71717a">
        ...........
      </text>
      <text x="960" y="226" fontFamily="ui-monospace,monospace" fontSize="11" fill="#4ade80">
        10 passed in 2.1s
      </text>
      <text x="960" y="256" fontFamily="ui-monospace,monospace" fontSize="11" fill="#79e6ff">
        $
      </text>
    </svg>
  );
}
