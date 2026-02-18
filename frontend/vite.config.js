import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// https://vite.dev/config/
export default defineConfig({
  plugins: [svelte()],
  server: {
    proxy: {
      // Proxy requests that start with '/api'
      '/api': {
        target: 'http://localhost:5000', // The target backend server
      },
    }
  }
})
