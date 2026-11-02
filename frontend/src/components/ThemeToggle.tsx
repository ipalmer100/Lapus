import { useEffect, useState } from 'react'
import { ORDER, THEME_LABELS, applyTheme, rememberTheme, storedTheme, type Theme } from '../theme'

/** Drawn rather than typed: a Unicode sun or moon renders differently on every
 *  platform and is missing outright from some Windows font stacks. */
function Icon({ theme }: { theme: Theme }) {
  if (theme === 'light') {
    return (
      <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
        <circle cx="8" cy="8" r="3.2" fill="currentColor" />
        {[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => (
          <line
            key={deg}
            x1="8" y1="1.3" x2="8" y2="3.1"
            stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"
            transform={`rotate(${deg} 8 8)`}
          />
        ))}
      </svg>
    )
  }
  if (theme === 'dark') {
    return (
      <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
        <path d="M13.2 10.1A5.6 5.6 0 0 1 6 2.8a5.7 5.7 0 1 0 7.2 7.3Z" fill="currentColor" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
      <rect x="1.8" y="2.6" width="12.4" height="8.4" rx="1.3" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <line x1="5.5" y1="13.6" x2="10.5" y2="13.6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  )
}

/** Cycles system → light → dark. The label says which state is in force, and
 *  the tooltip says what the next click will do. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(storedTheme)

  useEffect(() => {
    applyTheme(theme)
    rememberTheme(theme)
  }, [theme])

  const next = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length]

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={() => setTheme(next)}
      title={`Appearance: ${THEME_LABELS[theme]} — click for ${THEME_LABELS[next]}`}
      aria-label={`Appearance: ${THEME_LABELS[theme]}. Click for ${THEME_LABELS[next]}.`}
    >
      <Icon theme={theme} />
      <span className="theme-toggle-label">{THEME_LABELS[theme]}</span>
    </button>
  )
}
