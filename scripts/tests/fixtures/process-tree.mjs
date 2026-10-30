// 只创建空闲进程，不监听端口、不导入业务系统。
import { spawnManaged } from "../../managed-process.mjs";
import { spawn } from "node:child_process";

if (process.argv[2] === "ancestor-killed") {
  const launcher = spawn(process.execPath, [process.argv[1], "parent-killed"], {
    stdio: ["ignore", "pipe", "inherit"],
  });
  console.log(JSON.stringify({ launcher: launcher.pid }));
  launcher.stdout.on("data", (chunk) => process.stdout.write(chunk));
  launcher.on("exit", (code) => process.exit(code ?? 1));
} else {
  const code = `
  const { spawn } = require('node:child_process');
  const grandchild = spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], { stdio: 'ignore' });
  console.log(JSON.stringify({ child: process.pid, grandchild: grandchild.pid }));
  ${process.argv[2] === "normal" ? "setTimeout(() => process.exit(7), 200);" : "setInterval(() => {}, 1000);"}
`;
  const guard = spawnManaged(process.execPath, ["-e", code], { stdio: ["ignore", "pipe", "inherit"] });
  guard.stdout.on("data", (chunk) => process.stdout.write(chunk));
  guard.on("error", () => process.exit(1));
  guard.on("exit", (code) => process.exit(code ?? 1));
  console.log(JSON.stringify({ guard: guard.pid }));
}
