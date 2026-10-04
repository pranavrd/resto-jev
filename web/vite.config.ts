import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The places and review views call the FastAPI service (uvicorn streetwalker.api:app --port 8000) through /api.
// API_URL points the proxy elsewhere, e.g. API_URL=http://127.0.0.1:8001 npm run dev -- --port 5174
const apiUrl = process.env.API_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: apiUrl, rewrite: (path) => path.replace(/^\/api/, '') } },
  },
})
