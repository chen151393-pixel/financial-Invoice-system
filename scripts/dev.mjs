// 本地开发统一入口；不修改磁盘上的凭证和生产配置。
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { fileURLToPath } from "node:url";
import { readDevConfig } from "./dev-config.mjs";
import { spawnManaged } from "./managed-process.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const children = new Set();
let stopping = false;

function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  process.exitCode = code;
  for (const child of children) {
    if (process.platform === "win32" && child.pid) {
      // Windows 需同时结束包装脚本、Python 重载器及其工作进程。
      const killer = spawn("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
        stdio: "ignore",
        windowsHide: true,
      });
      killer.on("error", () => child.kill("SIGTERM"));
    } else child.kill("SIGTERM");
  }
}

function launch(name, args, env, cwd = root) {
  const child = spawnManaged(process.execPath, args, { cwd, stdio: "inherit", env });
  children.add(child);
  child.on("error", (error) => {
    console.error(`${name}启动失败：${error.message}；正在停止本次启动的服务。`);
    stop(1);
  });
  child.on("exit", (code) => {
    children.delete(child);
    if (!stopping) {
      console.error(`${name}已退出（退出码 ${code ?? "未知"}）；正在停止本次启动的服务。`);
      stop(code || 1);
    }
  });
}

async function checkPort(port, host) {
  await new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", () =>
      reject(new Error(`端口 ${port} 已被占用，请先停止原开发服务，再运行 npm.cmd run dev。`)),
    );
    server.listen(port, host, () => server.close(resolve));
  });
}

for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => stop());

try {
  const config = readDevConfig(root);
  const apiOnly = process.argv.includes("--api-only");
  const webOnly = process.argv.includes("--web-only");
  if (apiOnly && webOnly) throw new Error("不能同时指定 --api-only 与 --web-only");
  if (!webOnly) await checkPort(config.apiPort, "127.0.0.1");
  if (!apiOnly) await checkPort(config.webPort, "localhost");
  const env = {
    ...process.env,
    HOST: "127.0.0.1",
    PORT: String(config.apiPort),
    WEB_PORT: String(config.webPort),
    APP_ORIGIN: config.origin,
  };
  if (!webOnly) launch("后端", ["scripts/python.mjs", "-m", "backend", "--reload"], env);
  if (!apiOnly) {
    // 前端在 frontend/ 目录内运行，使用其自身依赖与 vite.config.ts。
    launch(
      "前端",
      ["node_modules/vite/bin/vite.js"],
      env,
      fileURLToPath(new URL("../frontend/", import.meta.url)),
    );
  }
  console.log(
    `${webOnly ? "" : `后端地址 ${config.apiTarget}；`}${apiOnly ? "" : `前端访问 ${config.origin}；`}Ctrl+C 停止本次启动的服务。`,
  );
} catch (error) {
  console.error(error.message);
  stop(1);
}
