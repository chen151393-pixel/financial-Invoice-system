import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { createServer } from "vite";

let server, Todos, Trend, Page, api;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  ({ WorkbenchTodos: Todos } = await server.ssrLoadModule(
    "/src/modules/matching/components/WorkbenchTodos.tsx",
  ));
  ({ WorkbenchTrend: Trend } = await server.ssrLoadModule(
    "/src/modules/matching/components/WorkbenchTrend.tsx",
  ));
  ({ WorkbenchPage: Page } = await server.ssrLoadModule("/src/modules/matching/pages/WorkbenchPage.tsx"));
  api = await server.ssrLoadModule("/src/modules/matching/api/workbench-api.ts");
});
after(async () => {
  await server?.close();
});
const counts = { all: 3, review: 1, matching: 1, task: 1, blocked: 0, reverify: 0, preparation: 1 };
const row = {
  key: "review:1",
  kind: "review",
  targetId: "1",
  title: "CD A&1",
  subtitle: "PL-1",
  party: "测试供应商",
  account: "A",
  amount: null,
  currency: "",
  amountLabel: "按子采购行核对",
  statusLabel: "待财务核对",
  reason: "核实依据",
  attention: false,
};
const data = {
  counts,
  filteredCounts: counts,
  items: [
    row,
    { ...row, key: "matching:2", kind: "matching", targetId: "2" },
    {
      ...row,
      key: "task:3",
      kind: "task",
      targetId: "3",
      amount: "9007199254740993.123456",
      currency: "CNY",
    },
  ],
  total: 3,
  page: 1,
  pages: 1,
  pageSize: 5,
  suppliers: [],
  trend: [],
  trendStart: "2026-10-13",
  trendEnd: "2026-10-19",
  latestInvoiceDate: "2026-10-19",
  unknownSupplierAmounts: 0,
};
const query = { account: "", keyword: "", kind: "all", sort: "priority", page: 1, pageSize: 5 };
const render = (component, props) =>
  renderToStaticMarkup(createElement(MemoryRouter, null, createElement(component, props)));

test("待办真实下钻到核对、发票比对和任务详情，金额保留精度", () => {
  const html = render(Todos, { data, query, change() {}, onExport() {}, exporting: false });
  assert.match(html, /href="\/review\?keyword=CD\+A%261&amp;account=A"/);
  assert.match(html, /href="\/matching\/2"/);
  assert.match(html, /href="\/tasks\/3"/);
  assert.match(html, /9,007,199,254,740,993.123456/);
  assert.match(html, /按子采购行核对/);
  assert.doesNotMatch(html, /模拟审核|超期/);
});

test("待办空结果明确显示，导出禁用", () => {
  const html = render(Todos, {
    data: { ...data, items: [], total: 0 },
    query,
    change() {},
    onExport() {},
    exporting: false,
  });
  assert.match(html, /当前条件下没有待办/);
  assert.match(html, /disabled=""[^>]*>↓ 导出全部结果/);
});

test("趋势只显示已开票，按币种逐日展示后端值与明确范围", () => {
  const html = render(Trend, {
    change() {},
    data: {
      ...data,
      trend: [{ currency: "USD", points: [{ date: "2026-10-19", amount: "120.500001", percent: "60.2" }] }],
    },
  });
  assert.match(html, /已开票金额趋势/);
  assert.match(html, /统计范围：2026-10-13 至 2026-10-19/);
  assert.match(html, /本月/);
  assert.match(html, /USD/);
  assert.match(html, /120.500001/);
  assert.match(html, /height:60.2%/);
  assert.match(html, /dateTime="2026-10-19"/);
  assert.equal((html.match(/role="listitem"/g) || []).length, 1);
  assert.doesNotMatch(html, /dateTime="2026-10-18"/);
  assert.doesNotMatch(html, /计划开票|超期/);
});

test("初始加载不显示伪造零指标或空结果", () => {
  const html = render(Page, {
    state: { query, loading: true, data: null, error: "", change() {}, refresh() {} },
  });
  assert.match(html, /正在读取工作台数据/);
  assert.doesNotMatch(html, /共 0 项|当前条件下没有待办/);
});

test("查询与导出携带相同筛选，导出结果完全取自后端", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return Response.json(
      url.endsWith("export") ? { filename: "result.csv", content: "真实导出", count: 52 } : data,
    );
  });
  const selected = { ...query, account: "A", keyword: "供应商", page: 2 };
  await api.queryWorkbench(selected);
  assert.equal((await api.exportWorkbench(selected)).count, 52);
  assert.deepEqual(
    calls.map((call) => call.body),
    [selected, selected],
  );
  assert.deepEqual(
    calls.map((call) => call.url),
    ["/api/matching/workbench/query", "/api/matching/workbench/export"],
  );
});
