import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { once } from "node:events";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import { setTimeout } from "node:timers/promises";
import test from "node:test";
import { spawnManaged } from "../managed-process.mjs";

const fixture = fileURLToPath(new URL("./fixtures/process-tree.mjs", import.meta.url));
const runner = fileURLToPath(new URL("../python.mjs", import.meta.url));
const windows = process.platform === "win32";

function alive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    if (error.code === "ESRCH") return false;
    throw error;
  }
}

async function waitGone(pids) {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (pids.every((pid) => !alive(pid))) return;
    await setTimeout(50);
  }
  assert.fail(`进程未退出：${pids.filter(alive).join(", ")}`);
}

for (const mode of ["normal", "parent-killed", "ancestor-killed", "guard-killed"]) {
  test(`Windows 进程组清理：${mode}`, { skip: !windows, timeout: 15000 }, async () => {
    const launcher = spawn(process.execPath, [fixture, mode], { stdio: ["ignore", "pipe", "pipe"] });
    const exited = once(launcher, "exit");
    const pids = {};
    let errors = "";
    launcher.stderr.on("data", (chunk) => (errors += chunk));
    const lines = createInterface({ input: launcher.stdout });
    try {
      for await (const line of lines) {
        Object.assign(pids, JSON.parse(line));
        if (pids.child) break;
      }
      assert.ok(pids.child && pids.grandchild && pids.guard, errors);
      assert.ok(alive(pids.grandchild), "测试孙进程必须先启动成功");
      if (mode === "parent-killed" || mode === "ancestor-killed") launcher.kill("SIGKILL");
      if (mode === "guard-killed") process.kill(pids.guard, "SIGKILL");
      const [code] = await exited;
      if (mode === "normal") assert.equal(code, 7, errors);
      await waitGone(Object.values(pids));
    } finally {
      lines.close();
      // 失败时只回收本用例创建的进程，绝不按端口或进程名清理。
      for (const pid of [launcher.pid, ...Object.values(pids)]) {
        if (alive(pid)) spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { windowsHide: true });
      }
    }
  });
}

test("Python 运行器保留退出码与标准输出", { timeout: 15000 }, async () => {
  const child = spawn(process.execPath, [runner, "-c", 'print("runner-ok"); raise SystemExit(7)']);
  let output = "";
  child.stdout.on("data", (chunk) => (output += chunk));
  const [code] = await once(child, "exit");
  assert.equal(code, 7);
  assert.match(output, /runner-ok/);
});

test("Windows 目标程序启动失败时守护器报错退出", { skip: !windows, timeout: 15000 }, async () => {
  const child = spawnManaged("invoice-test-missing-executable-6b77d9", [], {
    stdio: ["ignore", "ignore", "pipe"],
  });
  let errors = "";
  child.stderr.on("data", (chunk) => (errors += chunk));
  const [code] = await once(child, "exit");
  assert.equal(code, 1);
  assert.match(errors, /Windows 子进程管理失败/);
});
