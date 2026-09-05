import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Backend serves on 8015 (see app/core/config.py: api_port).
      '/api': {
        target: 'http://localhost:8015',
        changeOrigin: true,
      },
    },
  },
})
