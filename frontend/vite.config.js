import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'https://web-production-a92e6.up.railway.app',
        changeOrigin: true,
        secure: true,
      },
      '/health': {
        target: 'https://web-production-a92e6.up.railway.app',
        changeOrigin: true,
        secure: true,
      },
    },
  },
})
