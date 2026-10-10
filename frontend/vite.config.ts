import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

// 端口与后端地址取自仓库根目录的 .env / .env.local，进程环境变量优先（与 scripts/dev.mjs 一致）。
// 只在 Node 侧读取，不注入浏览器。
function port(env: Record<string, string>, key: string, fallback: number) {
  const value = String(env[key] ?? fallback).trim();
  if (!/^\d+$/.test(value) || Number(value) < 1 || Number(value) > 65535) {
    throw new Error(`${key} 必须为 1–65535 之间的整数端口`);
  }
  return Number(value);
}

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, fileURLToPath(new URL("../", import.meta.url)), "");
  const apiPort = port(env, "PORT", 3333);
  const webPort = port(env, "WEB_PORT", 5173);
  return {
    plugins: [react()],
    build: { outDir: "dist", emptyOutDir: true },
    server:
      command === "serve"
        ? {
            // 与开发入口 APP_ORIGIN 一致，避免点击 Vite 链接后被来源校验拒绝。
            host: "localhost",
            port: webPort,
            strictPort: true,
            proxy: {
              // 保留浏览器 Host，供后端校验本机会话的请求来源。
              "/api": { target: `http://127.0.0.1:${apiPort}`, changeOrigin: false },
            },
          }
        : undefined,
  };
});
