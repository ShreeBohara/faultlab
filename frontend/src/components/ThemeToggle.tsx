import { useEffect, useState } from 'react'

type Theme = 'dark' | 'light'

export function savedTheme(): Theme {
  try { return localStorage.getItem('faultlab:theme') === 'light' ? 'light' : 'dark' }
  catch { return 'dark' }
}

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#10121b' : '#f5f5f0')
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(savedTheme)
  useEffect(() => {
    applyTheme(theme)
    try { localStorage.setItem('faultlab:theme', theme) } catch { /* Theme still works when storage is unavailable. */ }
  }, [theme])
  const dark = theme === 'dark'
  return <button className="theme-toggle" type="button" aria-label={`Switch to ${dark ? 'light' : 'dark'} mode`} onClick={() => setTheme(dark ? 'light' : 'dark')}>
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {dark ? <><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" /></> : <path d="M20.8 13A9 9 0 0 1 11 3.2 9 9 0 1 0 20.8 13Z" />}
    </svg>
    <span>{dark ? 'Light mode' : 'Dark mode'}</span>
  </button>
}
