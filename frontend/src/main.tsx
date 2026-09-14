import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { EvidenceScreen } from './components/EvidenceScreen'
import { applyTheme, savedTheme } from './components/ThemeToggle'
import './styles.css'

applyTheme(savedTheme())
createRoot(document.getElementById('root')!).render(<StrictMode><EvidenceScreen /></StrictMode>)
