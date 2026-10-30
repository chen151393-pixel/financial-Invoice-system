import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

const localPython = fileURLToPath(
  new URL(
    process.platform === "win32" ? "../.venv/Scripts/python.exe" : "../.venv/bin/python",
    import.meta.url,
  ),
);
export const pythonExecutable =
  process.env.PYTHON_EXECUTABLE || (existsSync(localPython) ? localPython : "python");

export function spawnManaged(command, args, options = {}) {
  const env = options.env ?? process.env;
  // 后代自动继承同一个 Job，不重复创建嵌套守护器。
  if (process.platform !== "win32" || env.INVOICE_MANAGED_JOB === "1") {
    return spawn(command, args, options);
  }
  const guard = fileURLToPath(new URL("./windows_process_job.py", import.meta.url));
  return spawn(pythonExecutable, [guard, String(process.pid), command, ...args], {
    ...options,
    windowsHide: true,
    env: { ...env, PYTHONUTF8: "1" },
  });
}
