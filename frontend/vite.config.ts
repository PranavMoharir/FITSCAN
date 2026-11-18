import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  // One .env for the whole project: read VITE_* variables from the repository root.
  // Only variables starting with VITE_ are ever exposed to the browser code.
  envDir: '..',
  server: { port: 5173, strictPort: true },
})
