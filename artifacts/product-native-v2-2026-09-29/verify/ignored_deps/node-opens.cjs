// Independent verifier (native adapter v2), step 5: records every path under the repository that this Node
// process opens, reads or lists through node:fs (sync, callback and promise forms). Loads the verifier network guard too.
require('/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-native-v2-2026-09-29/verify/guard/node-guard.cjs')
const fs = require('node:fs'), path = require('node:path')
const R = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/', OUT = process.env.VERIFY_NODE_OPENS_LOG
const seen = new Set()
function note(p, kind) {
  try { if (typeof p === 'object' && p && p.href) p = new URL(p).pathname; if (typeof p !== 'string') return
    const abs = path.resolve(p); if (abs.startsWith(R)) seen.add(kind + abs.slice(R.length)) } catch {}
}
for (const [name, kind] of [['openSync', ''], ['readFileSync', ''], ['readdirSync', 'L '], ['open', ''], ['readFile', ''], ['readdir', 'L '], ['createReadStream', '']]) {
  const orig = fs[name]; if (typeof orig !== 'function') continue
  fs[name] = function (p, ...rest) { note(p, kind); return orig.call(this, p, ...rest) }
}
for (const [name, kind] of [['open', ''], ['readFile', ''], ['readdir', 'L ']]) {
  const orig = fs.promises[name]; if (typeof orig !== 'function') continue
  fs.promises[name] = function (p, ...rest) { note(p, kind); return orig.call(this, p, ...rest) }
}
process.on('exit', () => { if (OUT && seen.size) try { fs.appendFileSync(OUT, JSON.stringify({ pid: process.pid, argv: process.argv.slice(1, 4).join(' ').slice(0, 200), paths: [...seen].sort() }) + '\n') } catch {} })
