import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
    plugins: [react()],
    server: {
        host: '0.0.0.0',
        port: 5174,
        strictPort: true,
        proxy: {
            '/api': 'http://localhost:8000',
            '/health': 'http://localhost:8000',
        },
    },
    build: {
        outDir: '../src/backend/static',
        emptyOutDir: true,
    },
})
