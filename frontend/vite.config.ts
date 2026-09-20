import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'


// Set VITE_API_URL=https://api.colcar.tensorgeek.com/api in Vercel's environment
//       variables. api.ts already reads that variable.
//It is DONE,  Vercel  makes it hard with CNAME, but is is done now. 


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
      '/api': { // actually it is 8005 in my  VPS  port 
        target: 'http://localhost:8015',
        changeOrigin: true,
      },
      // Health routes live at the backend root, not under /api. Without this
      // the dev server answers /health with index.html.
      '/health': {
        target: 'http://localhost:8015',
        changeOrigin: true,
      },
    },
  },
})
