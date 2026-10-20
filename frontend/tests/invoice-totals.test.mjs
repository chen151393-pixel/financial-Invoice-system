import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

let server, View, api, Filters, emptyFilters, invoiceApi;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  ({ InvoiceSummary: View } = await server.ssrLoadModule(
    "/src/modules/invoice/components/InvoiceSummary.tsx",
  ));
  api = await server.ssrLoadModule("/src/modules/matching/api/index.ts");
  ({ InvoiceFilters: Filters, emptyFilters } = await server.ssrLoadModule(
    "/src/modules/invoice/components/InvoiceFilters.tsx",
  ));
  invoiceApi = await server.ssrLoadModule("/src/modules/invoice/api/invoice.ts");
});
after(async () => {
  await server?.close();
});

const data = {
  amounts: [
    {
      currency: "CNY",
      count: 50,
      gross: "2446196.97",
      tax: "281420.89",
      pendingAmount: "120.500001",
      pendingCount: 2,
      reviewAmount: "20.00",
      reviewCount: 1,
    },
  ],
};
const render = (props = {}) =>
  renderToStaticMarkup(createElement(View, { data, loading: false, error: "", ...props }));

test("展示后端全范围金额与计数，不在前端推算或截断小数", () => {
  const html = render();
  for (const value of [
    "2,446,196.97",
    "281,420.89",
    "120.500001",
    "20.00",
    "50 张发票",
    "2 张发票",
    "1 张发票",
  ])
    assert.ok(html.includes(value));
  assert.match(html, />票面税额</);
  assert.match(html, />待复核金额</);
  assert.doesNotMatch(html, /对应业务数据尚未接入|>可抵扣税额</);
});

test("加载和失败隐藏旧数值，空筛选与真实零金额分别显示", () => {
  for (const props of [{ loading: true }, { error: "读取失败" }]) {
    const html = render(props);
    assert.doesNotMatch(html, /2,446,196.97|>0.00</);
    assert.match(html, /正在统计|统计读取失败/);
  }
  assert.match(render({ data: { amounts: [] } }), /当前筛选无发票/);
  assert.match(
    render({ data: { amounts: [{ ...data.amounts[0], pendingAmount: "0", pendingCount: 0 }] } }),
    /¥ 0.00/,
  );
});

test("不同币种分行显示，未知金额不冒充零", () => {
  const html = render({
    data: { amounts: [data.amounts[0], { ...data.amounts[0], currency: "USD", tax: null }] },
  });
  assert.match(html, /USD 2,446,196.97/);
  assert.match(html, /USD —/);
});

test("统计请求只携带已应用筛选，不携带页码或金额", async (t) => {
  let seen;
  t.mock.method(globalThis, "fetch", async (url) => {
    seen = new URL(url, "http://localhost");
    return Response.json(data);
  });
  const result = await api.getInvoiceTotals({
    q: "测试供应商",
    account: "professional:account-a",
    status: "normal",
    date_from: "2026-10-01",
    date_to: "2026-10-19",
    page: 2,
    pageSize: 10,
    version: 1,
  });
  assert.deepEqual(result, data);
  assert.equal(seen.pathname, "/api/matching/invoice-totals");
  assert.deepEqual(Object.fromEntries(seen.searchParams), {
    q: "测试供应商",
    account: "professional:account-a",
    status: "normal",
    date_from: "2026-10-01",
    date_to: "2026-10-19",
  });
});

test("账套筛选展示后端名称、选中项和未应用提示，包含加载及失败状态", () => {
  const props = {
    draft: { ...emptyFilters, account: "account-a" },
    applied: emptyFilters,
    accounts: { items: [{ value: "account-a", label: "测试账套（专业版）" }], loading: false, error: "" },
    onChange() {},
    onSubmit() {},
    onReset() {},
    onRefresh() {},
    loading: false,
  };
  const html = renderToStaticMarkup(createElement(Filters, props));
  assert.match(html, /全部账套/);
  assert.match(html, /value="account-a" selected="">测试账套（专业版）/);
  assert.match(html, /当前结果仍对应上次查询/);
  for (const accounts of [
    { items: [], loading: true, error: "" },
    { items: [], loading: false, error: "账套选项读取失败" },
  ]) {
    const state = renderToStaticMarkup(createElement(Filters, { ...props, draft: emptyFilters, accounts }));
    assert.match(state, /select disabled=""/);
    assert.match(state, /正在读取账套|账套选项读取失败/);
  }
});

test("账套选项使用本地只读接口", async (t) => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "/api/sync/lemon/invoices/accounts");
    assert.equal(options.method, "GET");
    return Response.json({ items: [] });
  });
  assert.deepEqual(await invoiceApi.getInvoiceAccounts(), { items: [] });
});
