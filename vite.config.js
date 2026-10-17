import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// GitHub Pages serves this project from /utsavsync/; local dev remains at /.
export default defineConfig({
  base: process.env.GITHUB_ACTIONS === 'true' ? '/utsavsync/' : '/',
  plugins: [react()],
})