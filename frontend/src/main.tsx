import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { applyTheme, storedTheme } from './theme'
import './index.css'

// Applied before the first render so the page never paints in the wrong
// theme and then corrects itself.
applyTheme(storedTheme())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
