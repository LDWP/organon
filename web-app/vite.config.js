import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    proxy: {
      // avoids CORS issues in dev: the frontend calls /api/v1/...
      // relatively and Vite relays to the local FastAPI backend (see
      // src/api/client.js). The precise prefix '/api/v1' (not just '/api'):
      // Vite's proxy matches by raw string prefix, and '/api' also
      // intercepted JS module requests like /src/api/client.js.
      '/api/v1': {
        target: 'http://127.0.0.1:8123',
        changeOrigin: true,
      },
    },
  },
})
