import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { localPort, localUrl } from './local-ports.ts'

// Ports: FAULTLAB_DASHBOARD_PORT (default 5173) and FAULTLAB_BACKEND_PORT (default 8000).
const port = localPort('FAULTLAB_DASHBOARD_PORT')
const backend = localUrl('FAULTLAB_BACKEND_PORT')

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port,
    strictPort: true,
    proxy: {
      '/api': backend,
    },
  },
  preview: {
    host: '127.0.0.1',
    port,
    strictPort: true,
    proxy: {
      '/api': backend,
    },
  },
})
