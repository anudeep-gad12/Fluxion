const PROVIDERS = [
  { name: "Fireworks", hint: "api key" },
  { name: "ChatGPT / Codex", hint: "oauth" },
  { name: "Grok", hint: "oauth" },
  { name: "xAI", hint: "api key" },
  { name: "OpenRouter", hint: "api key" },
  { name: "DeepInfra", hint: "api key" },
  { name: "Local GGUF", hint: "llama.cpp" },
  { name: "MLX", hint: "Apple Silicon" },
] as const

export function ProviderStrip() {
  return (
    <section className="providerStrip container" aria-labelledby="provider-heading">
      <header className="providerStripHeader">
        <h2 id="provider-heading">Bring your own models &amp; keys.</h2>
        <p className="providerStripLead">
          Plug in hosted APIs, OAuth subscriptions, or local weights on your Mac — switch mid-thread without leaving
          the app.
        </p>
      </header>
      <ul className="providerGrid">
        {PROVIDERS.map((provider) => (
          <li key={provider.name} className="providerCard">
            <strong>{provider.name}</strong>
            <span>{provider.hint}</span>
          </li>
        ))}
      </ul>
      <ul className="providerFacts">
        <li>Switch models mid-thread</li>
        <li>Local + cloud in one app</li>
      </ul>
    </section>
  )
}
