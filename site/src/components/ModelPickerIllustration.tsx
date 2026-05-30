export function ModelPickerIllustration() {
  return (
    <svg
      className="productIllustration"
      viewBox="0 0 640 420"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Fluxion model picker"
    >
      <rect width="640" height="420" rx="16" fill="#0c0c0e" stroke="rgba(255,255,255,0.08)" />
      <text x="28" y="44" fontFamily="system-ui,sans-serif" fontSize="13" fontWeight="600" fill="#f4f4f5">
        Model
      </text>
      <rect x="28" y="58" width="584" height="48" rx="12" fill="#141416" stroke="rgba(121,230,255,0.35)" />
      <text x="44" y="88" fontFamily="system-ui,sans-serif" fontSize="14" fill="#f4f4f5">
        Qwen3-32B
      </text>
      <text x="500" y="88" fontFamily="system-ui,sans-serif" fontSize="12" fill="#71717a" textAnchor="end">
        DeepInfra
      </text>
      <rect x="28" y="120" width="584" height="272" rx="12" fill="#141416" stroke="rgba(255,255,255,0.06)" />
      <rect x="40" y="136" width="560" height="44" rx="8" fill="rgba(121,230,255,0.1)" stroke="rgba(121,230,255,0.2)" />
      <text x="56" y="164" fontFamily="system-ui,sans-serif" fontSize="13" fill="#79e6ff">
        Qwen3-32B · cloud
      </text>
      <text x="56" y="204" fontFamily="system-ui,sans-serif" fontSize="13" fill="#a1a1aa">
        Llama 3.3 70B · Fireworks
      </text>
      <text x="56" y="244" fontFamily="system-ui,sans-serif" fontSize="13" fill="#a1a1aa">
        gpt-oss-20b · local GGUF
      </text>
      <text x="56" y="284" fontFamily="system-ui,sans-serif" fontSize="13" fill="#71717a">
        Add provider…
      </text>
      <rect x="56" y="320" width="88" height="28" rx="14" fill="rgba(255,255,255,0.06)" />
      <text x="100" y="339" fontFamily="system-ui,sans-serif" fontSize="11" fill="#a1a1aa" textAnchor="middle">
        Chat
      </text>
      <rect x="156" y="320" width="88" height="28" rx="14" fill="rgba(121,230,255,0.18)" />
      <text x="200" y="339" fontFamily="system-ui,sans-serif" fontSize="11" fill="#79e6ff" textAnchor="middle">
        Agent
      </text>
      <rect x="256" y="320" width="100" height="28" rx="14" fill="rgba(255,255,255,0.06)" />
      <text x="306" y="339" fontFamily="system-ui,sans-serif" fontSize="11" fill="#a1a1aa" textAnchor="middle">
        Thinking
      </text>
    </svg>
  );
}
