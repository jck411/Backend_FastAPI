import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'
import { defineConfig } from 'vite'

// Use the same SSL certificates as the backend
const certPath = path.resolve(__dirname, '../certs/server.crt')
const keyPath = path.resolve(__dirname, '../certs/server.key')
const httpsConfig = fs.existsSync(certPath) && fs.existsSync(keyPath)
    ? { key: fs.readFileSync(keyPath), cert: fs.readFileSync(certPath) }
    : undefined

export default defineConfig({
    plugins: [react()],
    server: {
        host: '0.0.0.0',
        port: 5174,
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
        outDir: '../src/backend/static',
        emptyOutDir: true,
        // Memory optimization for local-only kiosk
        rollupOptions: {
            output: {
                manualChunks: undefined, // Single bundle for faster loading & less memory
                entryFileNames: 'assets/[name]-[hash].js',
                chunkFileNames: 'assets/[name]-[hash].js',
            }
        },
        target: 'es2020', // Modern target for smaller bundle
        minify: 'terser',
        terserOptions: {
            compress: {
                drop_console: true,    // Remove console.logs in production
                drop_debugger: true,   // Remove debugger statements
                pure_funcs: ['console.log', 'console.warn'], // Remove specific console calls
                reduce_vars: true,     // Reduce variable declarations
                dead_code: true,       // Remove unreachable code
            },
            mangle: {
                reserved: ['React', 'ReactDOM'], // Keep React globals
            }
        },
        // Reduce chunk size for better memory usage
        chunkSizeWarningLimit: 500,
    },
})
