import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

let server, api, View, Router;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  ({ LemonInvoiceView: View } = await server.ssrLoadModule("/src/modules/sync/LemonInvoiceView.tsx"));
  ({ MemoryRouter: Router } = await import("react-router"));
  api = await server.ssrLoadModule("/src/modules/sync/lemon-invoice-api.ts");
});
after(async () => {
  await server?.close();
});
const action = { allowed: true, reason: "可拉取" };
const config = {
  query: action,
  sync: action,
  selected: { asid: "7", name: "测试账套" },
  latest: null,
  defaultBusinessTypes: ["采购固定资产", "采购支出"],
  businessTypeOptions: ["采购固定资产", "采购支出", "办公费"],
};
const render = (data = config, extra = {}) =>
  renderToStaticMarkup(
    createElement(
      Router,
      {},
      createElement(View, {
        data,
        accounts: null,
        asid: "",
        setAsid() {},
        startDate: "",
        setStartDate() {},
        endDate: "",
        setEndDate() {},
        businessTypes: ["采购固定资产", "采购支出"],
        setBusinessTypes() {},
        busy: "",
        error: "",
        run() {},
        ...extra,
      }),
    ),
  );

test("拉取失败只提交一次，令牌和成功状态不由浏览器传入", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, options });
    return Response.json({ error: "结果待核实" }, { status: 503 });
  });
  const body = {
    asid: "7",
    startDate: "2026-10-01",
    endDate: "2026-10-16",
    requestId: "test-request",
    businessTypes: ["采购支出", "办公费"],
  };
  await assert.rejects(api.pullLemonInvoices(body), /待核实/);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/sync/lemon/invoices/pull-save");
  assert.deepEqual(JSON.parse(calls[0].options.body), body);
  assert.equal(calls[0].options.credentials, "same-origin");
});

test("查询原结果是只读请求，账号选择只提交账套编号", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, options });
    return Response.json({});
  });
  await api.queryLemonAccounts();
  assert.equal(calls[0].options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(calls[0].options.body), {});
  calls.length = 0;
  await api.getLemonRun("abc");
  await api.selectLemonAccount("7");
  assert.equal(calls[0].options.method, "GET");
  assert.deepEqual(JSON.parse(calls[1].options.body), { asid: "7" });
});

test("加载、错误、空账套与后端禁用原因明确", () => {
  assert.match(render(null), /正在读取同步配置/);
  assert.match(render(null, { error: "读取失败" }), /role="alert"/);
  assert.match(render(config, { accounts: [] }), /没有返回可用账套/);
  const html = render({ ...config, sync: { allowed: false, reason: "请先绑定" } });
  assert.match(html, /请先绑定/);
  assert.match(html, /disabled=""[^>]*>拉取并保存/);
  assert.match(html, /htmlFor|for="lemon-start"/);
});

test("执行中禁用重复操作，未知结果不冒充完成", () => {
  const latest = {
    requestId: "one",
    asid: "7",
    accountName: "测试账套",
    startDate: "2026-10-01",
    endDate: "2026-10-16",
    businessTypes: ["采购固定资产"],
    status: "running",
    result: null,
    error: null,
  };
  const html = render({ ...config, latest }, { busy: "pull" });
  assert.match(html, /结果待核实/);
  assert.doesNotMatch(html, /拉取结果已提交/);
  assert.ok(html.match(/<button[^>]*>/g).every((button) => button.includes('disabled=""')));
});

test("显示本次真实范围和提交统计，明细待补齐不声称已匹配", () => {
  const html = render({
    ...config,
    latest: {
      requestId: "one",
      asid: "7",
      accountName: "测试账套",
      startDate: "2026-10-01",
      endDate: "2026-10-16",
      businessTypes: ["采购固定资产", "采购支出"],
      status: "completed",
      error: null,
      result: {
        fetched: 3,
        excluded: 1,
        created: 1,
        updated: 0,
        unchanged: 1,
        pendingDetails: 2,
        message: "拉取结果已提交",
        saved: true,
      },
    },
  });
  assert.match(html, /2026-10-01/);
  assert.match(html, /拉取结果已提交/);
  assert.match(html, /明细待补齐/);
  assert.match(html, /暂不生成逐行匹配建议/);
});

test("业务类型由后端提供，多选和实际提交范围独立展示", () => {
  const html = render(config);
  assert.match(html, /保存的业务类型（可多选）/);
  assert.equal((html.match(/type="checkbox"/g) ?? []).length, 3);
  assert.equal((html.match(/checked=""/g) ?? []).length, 2);
  assert.match(html, /办公费/);
  assert.match(render(config, { busy: "pull" }), /<fieldset[^>]*disabled=""/);
});

test("全部跳过时展示后端未保存说明", () => {
  const html = render({
    ...config,
    latest: {
      requestId: "excluded",
      asid: "7",
      accountName: "测试账套",
      startDate: "2026-09-01",
      endDate: "2026-10-19",
      businessTypes: ["办公费"],
      status: "completed",
      error: null,
      result: {
        fetched: 7,
        excluded: 7,
        created: 0,
        updated: 0,
        unchanged: 0,
        pendingDetails: 0,
        saved: false,
        message: "读取 7 张，全部不在所选业务类型内，本次未保存发票。",
      },
    },
  });
  assert.match(html, /本次未保存发票/);
  assert.match(html, /本次业务类型：办公费/);
  assert.doesNotMatch(html, /保存成功|拉取结果已提交/);
});
