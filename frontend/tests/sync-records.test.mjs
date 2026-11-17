import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { createServer } from "vite";

let server, Records, api;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  ({ SyncRecords: Records } = await server.ssrLoadModule("/src/modules/sync/components/SyncRecords.tsx"));
  api = await server.ssrLoadModule("/src/modules/sync/api/history-api.ts");
});
after(async () => {
  await server?.close();
});

const render = (props) =>
  renderToStaticMarkup(createElement(MemoryRouter, null, createElement(Records, props)));
const common = {
  phase: "completed",
  label: "已完成",
  trigger: "schedule",
  finishedAt: "2026-11-16T18:01:00Z",
  message: "",
  created: 0,
  updated: 0,
  failed: 0,
};
const lemon = {
  ...common,
  requestId: "lemon-batch",
  source: "lemon",
  sourceLabel: "柠檬云发票",
  recordType: "lemon",
  kindLabel: "进项发票",
  rangeLabel: "开票日期",
  businessTypes: ["采购固定资产", "采购支出"],
  startDate: "2026-11-08",
  endDate: "2026-11-17",
  createdAt: "2026-11-16T18:00:00Z",
  fetched: 54,
};
const ns = {
  ...common,
  requestId: "ns-batch",
  source: "ns",
  sourceLabel: "NetSuite",
  recordType: "plan",
  kind: "customs-declarations",
  kindLabel: "报关单",
  rangeLabel: "创建日期",
  startDate: "2026-10-19",
  endDate: "2026-11-17",
  createdAt: "2026-11-16T17:59:00Z",
  fetched: 58,
  failed: 1,
};
const state = {
  data: { items: [lemon, ns], counts: { completed: 2 }, total: 2, pages: 1, page: 1, pageSize: 20 },
  phase: "",
  source: "",
  error: "",
  refresh() {},
  change() {},
};

test("合并记录按后端顺序展示 NS 与柠檬云，并各自进入原详情页", () => {
  const html = render({ state });
  assert.match(html, /同步执行记录/);
  assert.match(html, /按执行时间倒序/);
  assert.ok(html.indexOf("lemon-batch") < html.indexOf("ns-batch"), "保持后端给出的执行时间倒序");
  assert.match(html, /开票日期 · 采购固定资产、采购支出/);
  assert.match(html, /创建日期/);
  assert.match(html, /href="\/sync\/batches\/lemon-batch"/);
  assert.match(html, /href="\/sync\/ns\/batches\/ns-batch"/);
  assert.match(html, /全部来源/);
  assert.match(html, /已完成 2/);
});

test("合并记录覆盖加载、错误与空结果", () => {
  assert.match(render({ state: { ...state, data: null } }), /正在读取执行记录/);
  assert.match(render({ state: { ...state, data: null, error: "服务暂时不可用" } }), /执行记录读取失败/);
  assert.match(
    render({ state: { ...state, data: { ...state.data, items: [], total: 0, counts: {} } } }),
    /当前条件下没有执行记录/,
  );
});

test("合并记录接口把筛选交给后端", async () => {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url) => {
    calls.push(String(url));
    return new Response(JSON.stringify({ items: [] }), { headers: { "content-type": "application/json" } });
  };
  try {
    await api.listSyncRecords(2, "failed", "lemon");
  } finally {
    globalThis.fetch = original;
  }
  assert.match(calls[0], /\/api\/sync\/batches\?page=2&pageSize=20&phase=failed&source=lemon/);
});
