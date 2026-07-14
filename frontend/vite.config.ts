/// <reference types="vitest" />
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, '.', '')

    return {
        plugins: [react()],
        server: {
            host: true,
            port: 3000,
            proxy: {
                '/api': {
                    target: env.VITE_DEV_API_TARGET || 'http://127.0.0.1:8000',
                    changeOrigin: true,
                    rewrite: (path) => path.replace(/^\/api/, ''),
                },
            },
            watch: {
                usePolling: true
            }
        },
        test: {
            globals: true,
            environment: 'jsdom',
            setupFiles: ['./src/test/setup.ts'],
            include: ['src/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'],
            coverage: {
                provider: 'v8',
                reporter: ['text', 'lcov', 'html'],
                exclude: [
                    'node_modules/',
                    'src/test/',
                    '**/*.d.ts',
                ]
            }
        }
    }
})
