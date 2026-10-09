// Keep npm start available; the business service now runs in Python.
import { existsSync } from "node:fs";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const localPython = fileURLToPath(
  new URL(
    process.platform === "win32" ? "../.venv/Scripts/python.exe" : "../.venv/bin/python",
    import.meta.url,
  ),
);
const python = process.env.PYTHON_EXECUTABLE || (existsSync(localPython) ? localPython : "python");
const args = process.argv.slice(2);
// 当前 Uvicorn 的 Windows 重载会广播控制台 Ctrl+C，导致 npm/Vite 一起退出。
const windowsReload = process.platform === "win32" && args.includes("--reload");
if (windowsReload) {
  console.log("Windows 下已关闭 Python 自动重载；修改后端代码后请手动重启。前端热更新保留。");
}
const child = spawn(python, windowsReload ? args.filter((arg) => arg !== "--reload") : args, {
  cwd: root,
  stdio: "inherit",
  shell: false,
  env: { ...process.env, PYTHONUTF8: "1" },
});
child.on("error", () => {
  console.error("未找到 Python，请先建立 .venv 并安装 backend/requirements.txt");
  process.exitCode = 1;
});
child.on("exit", (code) => {
  process.exitCode = code ?? 1;
});
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    if (process.platform === "win32" && child.pid) {
      // 单独 dev:api 退出也不能留下子进程占用端口。
      const killer = spawn("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
        stdio: "ignore",
        windowsHide: true,
      });
      killer.on("error", () => child.kill(signal));
    } else child.kill(signal);
  });
}
