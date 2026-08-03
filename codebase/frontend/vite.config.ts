import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Port 8000 is occupied by the unrelated VLearn backend on this workspace.
// Proxy PDF Tutor requests to its dedicated FastAPI port instead.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
})
