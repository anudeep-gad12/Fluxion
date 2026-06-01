import ReactDOM from "react-dom/client"
import { CapabilityGrid } from "./components/CapabilityGrid"
import { InstallPreCta } from "./components/InstallPreCta"
import { OpenSourceSection } from "./components/OpenSourceSection"
import { ProviderStrip } from "./components/ProviderStrip"
import { FinalCta } from "./sections/FinalCta"
import { Footer } from "./sections/Footer"
import { Header } from "./sections/Header"
import { HeroSection } from "./sections/HeroSection"
import "./styles.css"

function App() {
  return (
    <div className="page">
      <Header />
      <main>
        <HeroSection />
        <ProviderStrip />
        <OpenSourceSection />
        <InstallPreCta />
        <CapabilityGrid />
        <FinalCta />
      </main>
      <Footer />
    </div>
  )
}

ReactDOM.createRoot(document.getElementById("root")!).render(<App />)
