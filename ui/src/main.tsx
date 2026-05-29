import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { applyDesktopPlatformClass, syncDesktopPlatformClassFromApi } from '@/lib/platform'
import './index.css'
import './styles/desktop-tokens.css'
import './styles/desktop-settings.css'
import './styles/desktop-thread.css'
import './styles/desktop-hud.css'
import './styles/tool-diff.css'
import App from './App.tsx'

applyDesktopPlatformClass()
void syncDesktopPlatformClassFromApi()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
