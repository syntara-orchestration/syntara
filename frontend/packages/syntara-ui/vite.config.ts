import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'
import svgr from 'vite-plugin-svgr'

import { isExtendedEnvValue, resolveAppTitleFromEnv } from './src/utils/buildFlags'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  const appTitle = resolveAppTitleFromEnv({
    extended: isExtendedEnvValue(env.VITE_EXTENDED),
    title: env.VITE_APP_TITLE,
  })

  const backendTarget = env.VITE_API_URL || 'http://localhost:3000'

  const proxyConfig = {
    '/api': {
      target: backendTarget,
      changeOrigin: true,
      secure: false,
    },
    // API docs live outside /api (Swagger/ReDoc/OpenAPI); keep UI proxy parity with nginx.
    '/api_docs': {
      target: backendTarget,
      changeOrigin: true,
      secure: false,
    },
    '/docs': {
      target: backendTarget,
      changeOrigin: true,
      secure: false,
    },
    '/health': {
      target: backendTarget,
      changeOrigin: true,
      secure: false,
    },
    '/ws': {
      target: env.VITE_WS_URL || backendTarget,
      changeOrigin: true,
      secure: false,
      ws: true,
    },
  }

  return {
    plugins: [
      react({
        babel: {
          plugins: [['babel-plugin-react-compiler']],
        },
      }),
      svgr(),
      {
        name: 'app-title',
        transformIndexHtml(html) {
          return html.replace(/<title>[^<]*<\/title>/, `<title>${appTitle}</title>`)
        },
      },
    ],
    build: {
      rollupOptions: {
        external: ['graphql', 'headers-polyfill'],
      },
    },
    server: {
      host: true,
      port: 5173,
      strictPort: true,
      proxy: proxyConfig,
      watch: {
        ignored: ['**/coverage/**', '**/playwright-report/**', '**/test-results/**'],
      },
    },
    preview: {
      host: true,
      port: 5173,
      strictPort: true,
      proxy: proxyConfig,
    },
  }
})
