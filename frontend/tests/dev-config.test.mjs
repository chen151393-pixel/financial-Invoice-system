import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { readDevConfig } from "../../scripts/dev-config.mjs";

test("开发启动仅使用 .env，忽略其他环境文件并保留进程配置", () => {
  const root = mkdtempSync(join(tmpdir(), "invoice-env-"));
  try {
    writeFileSync(join(root, ".env"), "PORT=4567\nWEB_PORT=4568\n");
    writeFileSync(join(root, ".env.local"), "PORT=9999\nWEB_PORT=9999\n");
    writeFileSync(join(root, ".env.development"), "PORT=9998\n");
    assert.equal(readDevConfig(root, {}).apiPort, 4567);
    assert.equal(readDevConfig(root, {}).webPort, 4568);
    assert.equal(readDevConfig(root, { PORT: "4569" }).apiPort, 4569);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
