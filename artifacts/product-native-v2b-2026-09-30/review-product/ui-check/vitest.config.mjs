// Reviewer-only config: runs ui-check/*.test.tsx against the frontend sources without touching frontend/.
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
const faultlab = fileURLToPath(new URL('../../../../', import.meta.url))
export default { plugins: [react()], server: { fs: { allow: [faultlab] } }, test: { include: ['*.test.tsx'] } }
