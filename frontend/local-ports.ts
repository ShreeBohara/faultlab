// Local service ports for the dev server, its /api proxy and the browser tests. One environment
// setting per service; unset or empty means the documented default (backend 8000, dashboard 5173).
// backend/app/ports.py and scripts/lib/ports.sh apply the same rule.
type Environment = Record<string, string | undefined>

export const DEFAULT_PORTS = { FAULTLAB_BACKEND_PORT: 8000, FAULTLAB_DASHBOARD_PORT: 5173 } as const
export type PortSetting = keyof typeof DEFAULT_PORTS

// Read without Node's type definitions, which this project does not install.
function processEnvironment(): Environment {
  return (globalThis as unknown as { process?: { env?: Environment } }).process?.env ?? {}
}

export function localPort(name: PortSetting, environment: Environment = processEnvironment()): number {
  const value = environment[name] ?? ''
  if (value === '') return DEFAULT_PORTS[name]
  if (!/^[1-9][0-9]{0,4}$/.test(value) || Number(value) > 65535) {
    throw new Error(`${name} must be a whole port number from 1 to 65535 (got '${value}').`)
  }
  return Number(value)
}

export function localUrl(name: PortSetting, environment: Environment = processEnvironment()): string {
  return `http://127.0.0.1:${localPort(name, environment)}`
}
