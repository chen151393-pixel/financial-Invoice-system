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
const child = spawn(python, process.argv.slice(2), {
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
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill(signal));
