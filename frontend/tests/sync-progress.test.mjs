import assert from "node:assert/strict";
import { before, after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

let server, api, PullProgress, PullResults;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  ({ PullResults } = await server.ssrLoadModule("/src/modules/sync/PullResults.tsx"));
  api = await server.ssrLoadModule("/src/modules/sync/api.ts");
  ({ PullProgress } = await server.ssrLoadModule("/src/modules/sync/PullProgress.tsx"));
});
after(async () => {
  await server?.close();
});

test("进度创建发送 JSON，保存保留日期、批次和进度身份", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, ...options });
    return Response.json(url.endsWith("/progress") ? { progressId: "abc" } : {});
  });
  const ticket = await api.createProgress();
  await api.pullRecords(
    "customs-declarations",
    20,
    { startDate: "2026-09-01", endDate: "2026-09-30" },
    true,
    ticket.progressId,
  );
  assert.equal(calls.length, 2);
  assert.equal(calls[0].headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(calls[1].body), {
    offset: 20,
    limit: 20,
    requireDateRange: true,
    partialSave: true,
    progressId: "abc",
    startDate: "2026-09-01",
    endDate: "2026-09-30",
  });
});

test("保存响应中断不会由接口层自动重试", async (t) => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async () => {
    calls++;
    throw new TypeError("network lost");
  });
  await assert.rejects(
    api.pullRecords(
      "customs-declarations",
      0,
      { startDate: "2026-09-01", endDate: "2026-09-30" },
      true,
      "abc",
    ),
    /连接已中断/,
  );
  assert.equal(calls, 1);
});

test("阶段计数可读且不虚构整体百分比，完成仍等待保存确认", () => {
  const progress = { state: "running", label: "读取报关明细", completed: 12, total: 40, elapsedSeconds: 8 };
  const render = (value, unavailable = false) =>
    renderToStaticMarkup(createElement(PullProgress, { progress: value, unavailable }));
  const html = render(progress);
  assert.match(html, /role="status"/);
  assert.match(html, /读取报关明细（12 \/ 40）/);
  assert.match(html, /已用时 8 秒/);
  assert.doesNotMatch(html, /%/);
  assert.match(render({ ...progress, state: "completed", label: "本批次已保存" }), /等待保存响应确认/);
  assert.match(render(progress, true), /请勿重复提交/);
  assert.equal(render(null), "");
});

test("逐单结果展示成功和失败，无成功时不伪造保存时间", () => {
  const result = {
    count: 2,
    pulledAt: "2026-10-16T01:00:00Z",
    message: "部分保存",
    dateRange: { label: "创建日期", startDate: "2026-09-01", endDate: "2026-09-30" },
    rows: [],
    storage: {
      savedAt: null,
      purchase: { created: 0, updated: 0, linesCreated: 0, linesUpdated: 0 },
      customs: { created: 0, updated: 0, linesCreated: 0, linesUpdated: 0 },
    },
    batch: {
      status: "partial",
      canContinue: true,
      counts: { saved: 1, failed: 1, unknown: 0, not_processed: 0 },
      items: [
        { id: "1", number: "SUB-001", status: "saved", reason: "已提交" },
        { id: "2", number: "SUB-002", status: "failed", reason: "单价格式不合规" },
      ],
    },
  };
  const html = renderToStaticMarkup(createElement(PullResults, { result }));
  assert.match(html, /SUB-001/);
  assert.match(html, /SUB-002/);
  assert.match(html, /失败，未保存/);
  assert.match(html, /单价格式不合规/);
  assert.match(html, /本批暂无确认成功的保存记录/);
  assert.doesNotMatch(html, /Invalid Date|1970/);
});
