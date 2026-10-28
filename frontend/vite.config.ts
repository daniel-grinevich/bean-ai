import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [vue(), tailwindcss()],
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    // shadcn/reka-ui + TanStack make a ~700 kB vendor chunk; Shiki grammars are split out.
    build: { chunkSizeWarningLimit: 800 },
    server: {
      port: Number(env.VITE_PORT ?? 5173),
      proxy: {
        // Backend URL for the dev proxy, e.g. VITE_API_TARGET=http://localhost:8010
        '/api': env.VITE_API_TARGET ?? 'http://localhost:8000',
      },
    },
  }
})
