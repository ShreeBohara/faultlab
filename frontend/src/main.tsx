import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

type HealthState =
  | { state: 'loading' }
  | { state: 'connected'; status: string; service: string }
  | { state: 'error'; message: string }

function App() {
  const [health, setHealth] = useState<HealthState>({ state: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    let timedOut = false
    const timeout = window.setTimeout(() => {
      timedOut = true
      controller.abort()
    }, 8000)

    async function checkHealth() {
      try {
        const response = await fetch('/api/health', { signal: controller.signal })
        if (!response.ok) throw new Error(`The backend returned HTTP ${response.status}.`)
        const data: unknown = await response.json()
        if (
          typeof data !== 'object' ||
          data === null ||
          !('status' in data) ||
          !('service' in data) ||
          data.status !== 'ok' ||
          data.service !== 'faultlab-backend'
        ) {
          throw new Error('The backend returned an unexpected health response.')
        }
        if (active) setHealth({ state: 'connected', status: data.status, service: data.service })
      } catch (error) {
        if (active) {
          setHealth({
            state: 'error',
            message: timedOut
              ? 'The backend did not respond within 8 seconds.'
              : error instanceof Error
                ? error.message
                : 'The backend could not be reached.',
          })
        }
      } finally {
        window.clearTimeout(timeout)
      }
    }

    void checkHealth()
    return () => {
      active = false
      window.clearTimeout(timeout)
      controller.abort()
    }
  }, [attempt])

  return (
    <main className="workspace">
      <header className="masthead">
        <span className="monogram" aria-hidden="true">FL</span>
        <span className="environment">Local development</span>
      </header>

      <div className="intro">
        <p className="eyebrow">A foundation to build on</p>
        <h1>FaultLab</h1>
        <p className="byline">Built by Gatekeeper.</p>
        <p className="description">
          Getting the workspace connected. Product design and architecture are still in progress.
        </p>
      </div>

      <section className="connection" aria-labelledby="connection-title">
        <div className="connection-heading">
          <h2 id="connection-title">Backend connection</h2>
          <code>GET /api/health</code>
        </div>
        <div role="status" aria-live="polite" aria-atomic="true" className="health-result">
          <p className={`status status-${health.state}`}>
            <span className="status-dot" aria-hidden="true" />
            {health.state === 'loading' && 'Checking connection…'}
            {health.state === 'connected' && 'Backend connected'}
            {health.state === 'error' && 'Backend unavailable'}
          </p>
          {health.state === 'loading' && <p className="hint">Waiting for the local backend.</p>}
          {health.state === 'connected' && (
            <dl className="response">
              <div><dt>Status</dt><dd><code>{health.status}</code></dd></div>
              <div><dt>Service</dt><dd><code>{health.service}</code></dd></div>
            </dl>
          )}
          {health.state === 'error' && (
            <div className="error-detail">
              <p>{health.message}</p>
              <p>Start the backend with <code>./scripts/start-backend.sh</code> from the repository root, then try again.</p>
            </div>
          )}
        </div>
        <button
          type="button"
          disabled={health.state === 'loading'}
          onClick={() => {
            setHealth({ state: 'loading' })
            setAttempt((current) => current + 1)
          }}
        >
          {health.state === 'loading' ? 'Checking…' : 'Check again'}
        </button>
      </section>
      <footer>Setup check · No provider calls</footer>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
