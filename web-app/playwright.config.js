import { defineConfig } from '@playwright/test'

// Dedicated port: never reuse (or collide with) a dev server the user
// already runs on 5173.
const PORT = 5174

export default defineConfig({
  testDir: 'e2e',
  workers: 1,
  // The existing specs select by French text: force the browser language
  // so they stay on `fr` whatever locales get enabled later.
  use: { baseURL: `http://localhost:${PORT}`, viewport: { width: 1280, height: 720 }, locale: 'fr-FR' },
  webServer: {
    command: `npx vite --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: false,
  },
})
