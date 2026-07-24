import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // évite les soucis de CORS en dev : le frontend appelle /api/v1/... en relatif,
      // Vite relaie vers le backend FastAPI local (voir apiClient.js). Préfixe précis
      // '/api/v1' (pas juste '/api') : le proxy de Vite matche par préfixe de chaîne brut,
      // '/api' interceptait aussi les requêtes de modules JS comme /apiClient.js.
      '/api/v1': {
        target: 'http://127.0.0.1:8123',
        changeOrigin: true,
      },
    },
  },
})
