import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { EvidenceScreen } from './components/EvidenceScreen'
import './styles.css'

createRoot(document.getElementById('root')!).render(<StrictMode><EvidenceScreen /></StrictMode>)
