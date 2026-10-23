import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
    // loadEnv 读取 .env / .env.local 等（含 VITE_ 前缀变量）
    const env = loadEnv(mode, '.', '');
    return {
      server: {
        port: 3000,
        host: '0.0.0.0',
        // 开发期 API 代理：前端默认走相对路径 /api/v1（src/services/api/http.ts 的
        // BASE_URL 兜底值），请求落在 Vite dev server 自身，必须由此代理转发到后端，
        // 否则全部接口 404。后端地址默认 http://localhost:8000（server/config.yaml
        // 默认端口），可用 VITE_API_PROXY_TARGET 覆盖（如指向局域网内另一台机器的后端）。
        // 直连后端（不走代理）时改设 VITE_API_BASE_URL=http://<host>:8000/api/v1，见 README。
        proxy: {
          '/api': {
            target: env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000',
            changeOrigin: true,
          },
        },
      },
      plugins: [react()],
      resolve: {
        alias: {
          '@': path.resolve(__dirname, '.'),
        }
      }
    };
});
