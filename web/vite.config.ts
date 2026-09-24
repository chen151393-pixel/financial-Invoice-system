import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { readDevConfig } from "../scripts/dev-config.mjs";

export default defineConfig(({ command }) => {
  const config = command === "serve" ? readDevConfig(fileURLToPath(new URL("../", import.meta.url))) : null;
  return {
    root: fileURLToPath(new URL(".", import.meta.url)),
    publicDir: "../public",
    plugins: [react()],
    build: { outDir: "../dist/web", emptyOutDir: true },
    server: config
      ? {
          // 与开发入口 APP_ORIGIN 一致，避免点击 Vite 链接后被来源校验拒绝。
          host: "localhost",
          port: config.webPort,
          strictPort: true,
          proxy: {
            // 保留浏览器 Host，供后端校验本机会话的请求来源。
            "/api": { target: config.apiTarget, changeOrigin: false },
          },
        }
      : undefined,
  };
});
