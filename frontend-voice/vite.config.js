import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import { defineConfig } from 'vite'

// Use the same SSL certificates as the backend
const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const certPath = path.resolve(__dirname, '../certs/server.crt')
const keyPath = path.resolve(__dirname, '../certs/server.key')
const httpsConfig = fs.existsSync(certPath) && fs.existsSync(keyPath)
  ? { key: fs.readFileSync(keyPath), cert: fs.readFileSync(certPath) }
  : undefined

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5175,
    strictPort: true,
    https: httpsConfig,
    proxy: {
      '/api': {
        target: 'https://localhost:8000',
        secure: false, // Accept self-signed certs
      },
      '/health': {
        target: 'https://localhost:8000',
        secure: false,
      },
    },
  },
  build: {
    outDir: '../src/backend/static/voice',
    emptyOutDir: true,
  },
  base: '/voice/',
})
