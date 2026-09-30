// Independent verifier guard (reused from the discovery v3 verifier, reviewed 2026-09-29 for product dependability), loaded into every Node process via
// NODE_OPTIONS=--require. Logs and REFUSES any non-loopback TCP connect or DNS lookup made from Node,
// and logs one 'guard_loaded' line per process so the log proves the guard was active.
const net = require('node:net'), dns = require('node:dns'), fs = require('node:fs')
const LOG = process.env.VERIFY_NODE_GUARD_LOG
function isLocal(h) {
  if (h == null) return true
  const s = String(h).replace(/^\[|\]$/g, '').split('%')[0].toLowerCase()
  if (s === '' || s === 'localhost' || s.endsWith('.localhost')) return true
  if (net.isIPv4(s)) return s.startsWith('127.') || s === '0.0.0.0'
  if (net.isIPv6(s)) {
    const m = s.match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/); if (m) return isLocal(m[1])
    // Expand '::' and compare numerically: only :: (unspecified) and ::1 (loopback) are local. (Revision 2: the first
    // version missed the fully written-out form 0000:...:0000 that vite looks up at startup.)
    const [a, b = ''] = s.split('::'); const A = a ? a.split(':') : [], B = b ? b.split(':') : []
    const all = s.includes('::') ? [...A, ...Array(8 - A.length - B.length).fill('0'), ...B] : A
    const v = all.map(x => parseInt(x || '0', 16))
    return v.length === 8 && v.slice(0, 7).every(x => x === 0) && (v[7] === 0 || v[7] === 1)
  }
  return false
}
function log(event, host) {
  if (!LOG) return
  try { fs.appendFileSync(LOG, JSON.stringify({ t: Date.now(), pid: process.pid, event, host: String(host), argv: process.argv.slice(1, 3).join(' ').slice(0, 160) }) + '\n') } catch {}
}
log('guard_loaded', process.execPath)
const origConnect = net.Socket.prototype.connect
net.Socket.prototype.connect = function (...args) {
  let o = args[0]; if (Array.isArray(o)) o = o[0]
  let host
  if (o && typeof o === 'object') host = o.path ? null : (o.host ?? 'localhost')
  else if (typeof o === 'number' || /^\d+$/.test(String(o))) host = typeof args[1] === 'string' ? args[1] : 'localhost'
  else host = null  // unix socket path
  if (host !== null && !isLocal(host)) { log('REFUSED_connect', host); throw new Error('verify node guard: outside connect refused') }
  return origConnect.apply(this, args)
}
const origLookup = dns.lookup
dns.lookup = function (host, ...rest) {
  if (!isLocal(host)) {
    log('REFUSED_lookup', host)
    const cb = rest[rest.length - 1]
    const e = Object.assign(new Error('verify node guard: outside lookup refused'), { code: 'ENOTFOUND' })
    if (typeof cb === 'function') return process.nextTick(cb, e)
    throw e
  }
  return origLookup.call(this, host, ...rest)
}
const origP = dns.promises.lookup
dns.promises.lookup = async function (host, ...rest) {
  if (!isLocal(host)) { log('REFUSED_lookup', host); throw Object.assign(new Error('verify node guard: outside lookup refused'), { code: 'ENOTFOUND' }) }
  return origP.call(this, host, ...rest)
}
