import { svelte } from '@sveltejs/vite-plugin-svelte'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [svelte()],
  server: {
    host: '0.0.0.0', // Listen on all network interfaces
    port: 5173,
    strictPort: true, // Fail if port is in use (we kill it via start_server.sh)
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
})
