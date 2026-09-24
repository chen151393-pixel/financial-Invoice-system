import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { parseEnv } from "node:util";

// 仅在启动进程中读取配置，不向浏览器注入根目录中的凭证。
export function readDevConfig(root, environment = process.env) {
  let values = {};
  for (const name of [".env", ".env.local"]) {
    try {
      values = { ...values, ...parseEnv(readFileSync(resolve(root, name), "utf8")) };
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
  }
  values = { ...values, ...environment };
  function port(key, fallback) {
    const value = String(values[key] ?? fallback).trim();
    if (!/^\d+$/.test(value) || Number(value) < 1 || Number(value) > 65535) {
      throw new Error(`${key} 必须为 1–65535 之间的整数端口`);
    }
    return Number(value);
  }
  const apiPort = port("PORT", 3333);
  const webPort = port("WEB_PORT", 5173);
  if (apiPort === webPort) throw new Error("PORT 与 WEB_PORT 不能使用相同端口");
  return {
    apiPort,
    webPort,
    origin: `http://localhost:${webPort}`,
    apiTarget: `http://127.0.0.1:${apiPort}`,
  };
}
