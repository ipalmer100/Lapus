import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // In development the UI runs on Vite's port and the API on the backend's.
    // Proxying /api keeps the frontend code free of environment-dependent
    // base URLs -- in the packaged app both are served from one origin, and
    // this makes development behave the same way.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8770',
        changeOrigin: true,
      },
    },
  },
})
