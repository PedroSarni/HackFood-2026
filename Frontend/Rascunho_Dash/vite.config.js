import { defineConfig } from 'vite';

// /api vai pro servidor local do painel (src/painel/servidor.py, porta 8787)
export default defineConfig({
  server: { proxy: { '/api': { target: 'http://127.0.0.1:8787', changeOrigin: true } } },
});
