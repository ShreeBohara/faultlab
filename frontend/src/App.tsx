import { useEffect, useRef, useState } from 'react'
import { EvidenceScreen } from './components/EvidenceScreen'
import { StudiesScreen } from './components/StudiesScreen'
import { studiesRoute } from './studies'

/** Two pages on one hash: the campaign screen (default) and the saved study results (#/studies, #/studies/<id>). */
export function App() {
  const [hash, setHash] = useState(() => window.location.hash)
  useEffect(() => {
    const update = () => setHash(window.location.hash)
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  const studies = studiesRoute(hash)
  const page = studies ? 'studies' : 'campaigns'
  useEffect(() => { document.title = page === 'studies' ? 'Study results · FaultLab' : 'FaultLab' }, [page])
  // A different page starts at its top; the browser keeps the old scroll position on a hash change otherwise.
  const first = useRef(true)
  useEffect(() => { if (first.current) { first.current = false; return } window.scrollTo?.(0, 0) }, [page])
  return studies ? <StudiesScreen selectedId={studies.id} /> : <EvidenceScreen />
}
