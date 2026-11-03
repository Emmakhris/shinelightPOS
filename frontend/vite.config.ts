import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backend = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // reachable from other tills/tablets on the shop network during development
    proxy: { '/api': backend, '/media': backend },
  },
})
