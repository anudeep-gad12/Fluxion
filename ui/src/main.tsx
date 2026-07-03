import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { applyDesktopPlatformClass, syncDesktopPlatformClassFromApi } from '@/lib/platform'
import { ThemeProvider } from '@/hooks/useTheme'
import './styles/tokens.css'
import './index.css'
import './styles/shell.css'
import './styles/desktop-settings.css'
import './styles/overlay.css'
import './styles/transcript.css'
import App from './App.tsx'

applyDesktopPlatformClass()
void syncDesktopPlatformClassFromApi()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ThemeProvider>
  </StrictMode>,
)
