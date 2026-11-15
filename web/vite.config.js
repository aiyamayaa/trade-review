import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

// 开发时 Vite 跑在 5173，Node 后端 API 跑在 8788
// 所有 /api 请求由 Vite 代理到 Node 后端，避免跨域
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8788',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
