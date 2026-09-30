import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Relative asset base so the production build also loads from disk
  // (Electron loadFile) -- `vite dev` / `vite preview` are unaffected.
  base: './',
})
