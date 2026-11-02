/**
 * Light / dark / follow-the-system.
 *
 * Three states rather than two, because "follow the system" is what most
 * people actually want and it is what the app did before this existed.
 * Forcing a choice would be a downgrade for anyone whose machine already
 * switches at dusk.
 *
 * Kept apart from the button so this file exports no component -- it is also
 * imported by main.tsx, which applies the stored choice before first render
 * so the page never flashes the wrong theme.
 */
export type Theme = 'system' | 'light' | 'dark'

const STORAGE_KEY = 'lapus.theme'
export const ORDER: Theme[] = ['system', 'light', 'dark']

export const THEME_LABELS: Record<Theme, string> = {
  system: 'Match system',
  light: 'Light',
  dark: 'Dark',
}

export function storedTheme(): Theme {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw === 'light' || raw === 'dark' || raw === 'system' ? raw : 'system'
  } catch {
    // Private windows and locked-down group policy can both make
    // localStorage throw rather than return null.
    return 'system'
  }
}

export function rememberTheme(theme: Theme): void {
  try {
    localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    // A preference that cannot be saved still applies for this session.
  }
}

/**
 * Applied to <html>, which the stylesheet keys off. "system" removes the
 * attribute entirely rather than setting a third value, so the
 * prefers-color-scheme rules take over on their own.
 */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  if (theme === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', theme)
}
