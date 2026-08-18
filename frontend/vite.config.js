import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    port: 3000,
    // En desarrollo /api se redirige al backend FastAPI. Si no está levantado,
    // la capa de datos cae a los fixtures y la interfaz lo indica.
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // El bundle de la aplicación queda en ~215 kB; el chunk grande restante es
    // fixtures.json, que solo se descarga si la API no responde.
    chunkSizeWarningLimit: 800
  }
})
