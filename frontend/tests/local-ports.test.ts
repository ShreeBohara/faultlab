import { describe, expect, it } from 'vitest'
import { DEFAULT_PORTS, localPort, localUrl } from '../local-ports'

describe('local service ports', () => {
  it('keeps the documented defaults when nothing is set', () => {
    expect(DEFAULT_PORTS).toEqual({ FAULTLAB_BACKEND_PORT: 8000, FAULTLAB_DASHBOARD_PORT: 5173 })
    expect(localPort('FAULTLAB_DASHBOARD_PORT', {})).toBe(5173)
    expect(localPort('FAULTLAB_BACKEND_PORT', { FAULTLAB_BACKEND_PORT: '' })).toBe(8000)
    expect(localUrl('FAULTLAB_BACKEND_PORT', {})).toBe('http://127.0.0.1:8000')
  })

  it('uses one setting per service', () => {
    const environment = { FAULTLAB_BACKEND_PORT: '18000', FAULTLAB_DASHBOARD_PORT: '15173' }
    expect(localPort('FAULTLAB_DASHBOARD_PORT', environment)).toBe(15173)
    expect(localUrl('FAULTLAB_BACKEND_PORT', environment)).toBe('http://127.0.0.1:18000')
    expect(localPort('FAULTLAB_BACKEND_PORT', { FAULTLAB_BACKEND_PORT: '65535' })).toBe(65535)
  })

  it('refuses anything that is not a whole port number from 1 to 65535', () => {
    for (const value of ['0', '65536', '08000', 'abc', ' 8000', '80 00', '-1', '8000.5']) {
      expect(() => localPort('FAULTLAB_DASHBOARD_PORT', { FAULTLAB_DASHBOARD_PORT: value }))
        .toThrow(`FAULTLAB_DASHBOARD_PORT must be a whole port number from 1 to 65535 (got '${value}').`)
    }
  })
})
