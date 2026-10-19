import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

let server, api, View, Table, Filters, Drawer;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  api = await server.ssrLoadModule("/src/modules/invoice/api/detail-refresh.ts");
  ({ InvoiceDetailRefresh: View } = await server.ssrLoadModule(
    "/src/modules/invoice/components/InvoiceDetailRefresh.tsx",
  ));
  ({ InvoiceTable: Table } = await server.ssrLoadModule("/src/modules/invoice/components/InvoiceTable.tsx"));
  ({ InvoiceFilters: Filters } = await server.ssrLoadModule(
    "/src/modules/invoice/components/InvoiceFilters.tsx",
  ));
  ({ InvoiceDetailDrawer: Drawer } = await server.ssrLoadModule(
    "/src/modules/invoice/components/InvoiceDetailDrawer.tsx",
  ));
});
after(async () => {
  await server?.close();
});
const state = {
  selected: ["1"],
  actions: { 1: { allowed: true, reason: "可补拉" } },
  busy: false,
  blocked: false,
  error: "",
  run: null,
  pending: "",
  execute() {},
  select() {},
  selectAll() {},
};
const render = (extra = {}) => renderToStaticMarkup(createElement(View, { state: { ...state, ...extra } }));

test("单张批量提交都只带 ID 和请求编号，结果查询不重放写入", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, options });
    return Response.json({ status: "running" });
  });
  await api.refreshInvoiceDetails(["1"], "single");
  await api.refreshInvoiceDetails(["1", "2"], "batch");
  await api.getDetailRun("batch");
  assert.deepEqual(JSON.parse(calls[0].options.body), { invoiceIds: ["1"], requestId: "single" });
  assert.deepEqual(JSON.parse(calls[1].options.body), { invoiceIds: ["1", "2"], requestId: "batch" });
  assert.equal(calls[2].options.method, "GET");
  assert.equal(calls[2].url, "/api/sync/lemon/runs/batch");
});
test("接口失败不假报成功或自动重试", async (t) => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async () => {
    calls++;
    return Response.json({ error: "上游不可用" }, { status: 502 });
  });
  await assert.rejects(api.refreshInvoiceDetails(["1"], "single"), /上游不可用/);
  assert.equal(calls, 1);
});
test("未选时隐藏补拉栏，选中后提供批量操作，未知结果提供查询", () => {
  assert.equal(render({ selected: [] }), "");
  assert.doesNotMatch(render(), /查询补拉状态|仅选当前页|从当前绑定的原账套补拉/);
  for (const extra of [{ actions: {} }, { blocked: true }])
    assert.match(render(extra), /disabled=""[^>]*>重新拉取商品明细/);
  const html = render({ pending: "原请求", blocked: true });
  assert.match(html, /结果待核实/);
  assert.match(html, /查询补拉状态/);
  assert.doesNotMatch(html, /明细完整 1/);
});
test("展示真实空明细原因及完整计数", () => {
  const html = render({
    run: {
      status: "completed",
      result: {
        message: "未新增或更新",
        completeDetails: 0,
        pendingDetails: 1,
        detailIssueCount: 1,
        detailIssues: [{ number: "26952", reason: "柠檬云明细接口返回空商品行" }],
      },
    },
  });
  assert.match(html, /明细完整 0 张/);
  assert.match(html, /26952：柠檬云明细接口返回空商品行/);
  assert.match(render({ error: "读取失败" }), /role="alert"/);
});
test("列表提供行选择及单张补拉，后端禁用原因可见", () => {
  const html = renderToStaticMarkup(
    createElement(Table, {
      rows: [{ id: "1", number: "26001", importedAt: "2026-10-19T00:00:00Z" }],
      matching: {},
      matchingError: "",
      onMatch() {},
      onDetail() {},
      refresh: { ...state, actions: { 1: { allowed: false, reason: "当前账套与发票原账套不一致" } } },
    }),
  );
  assert.match(html, /选择发票26001/);
  assert.match(html, /选择本页可补拉发票/);
  assert.match(html, /当前账套与发票原账套不一致/);
  assert.match(html, /disabled=""[^>]*>重新拉取商品明细/);
});

test("票面状态筛选常驻查询栏，折叠日期筛选时仍可选择", () => {
  const html = renderToStaticMarkup(
    createElement(Filters, {
      draft: { q: "", status: "void", date_from: "", date_to: "" },
      loading: false,
      onChange() {},
      onSubmit() {},
      onReset() {},
      onRefresh() {},
    }),
  );
  assert.match(html, /<label[^>]*>票面状态<select/);
  assert.match(html, /value="void" selected=""/);
  assert.match(html, /value="red_offset">已被红冲/);
  assert.match(html, /value="red_letter">红字发票/);
  assert.doesNotMatch(html, /id="invoice-more-filters"/);
});

test("仅状态标签高亮，前端按后端展示分类区分红字与被红冲原票", () => {
  for (const [displayStatus, status] of [
    ["red_offset", "已被红冲"],
    ["red_letter", "红字发票"],
    ["void", "作废"],
    ["normal", "正常"],
  ]) {
    const html = renderToStaticMarkup(
      createElement(Table, {
        rows: [
          {
            id: "1",
            number: "26001",
            sourceStatus: "normal",
            displayStatus,
            status,
            gross: "-113.00",
            currency: "CNY",
            importedAt: "2026-10-19T00:00:00Z",
          },
        ],
        matching: {},
        matchingError: "",
        onMatch() {},
        onDetail() {},
      }),
    );
    assert.doesNotMatch(html, /invoice-status-row--/);
    assert.match(html, new RegExp(`invoice-status-badge--${displayStatus}`));
    assert.ok(html.includes(status));
    assert.match(html, /-113.00/);
    assert.match(html, /票面详情/);
  }
});

test("详情显示后端状态提示，未提供关联票号时不伪造链接", () => {
  const html = renderToStaticMarkup(
    createElement(Drawer, {
      detail: {
        id: "1",
        sourceStatus: "void",
        status: "作废",
        statusNotice: "此发票已作废，请复核历史记录。",
        lines: [],
      },
      error: "",
      onClose() {},
      onMatch() {},
    }),
  );
  assert.match(html, /invoice-status-badge--void/);
  assert.match(html, /此发票已作废，请复核历史记录/);
  assert.doesNotMatch(html, /关联发票.*href=/);
});
