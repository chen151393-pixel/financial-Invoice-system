import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { createServer } from "vite";

let server, Plan, Batch, Scope, Detail, api;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  ({ SyncPlanForm: Plan } = await server.ssrLoadModule("/src/modules/sync/components/SyncPlanForm.tsx"));
  ({ SyncBatchForm: Batch } = await server.ssrLoadModule("/src/modules/sync/components/SyncBatchForm.tsx"));
  ({ SyncAccountScope: Scope } = await server.ssrLoadModule(
    "/src/modules/sync/components/SyncAccountScope.tsx",
  ));
  ({ SyncBatchDetailPage: Detail } = await server.ssrLoadModule(
    "/src/modules/sync/pages/SyncBatchDetailPage.tsx",
  ));
  api = await server.ssrLoadModule("/src/modules/sync/api/background-api.ts");
});
after(async () => {
  await server?.close();
});
const data = {
  submit: { allowed: true, reason: "可提交" },
  pause: { allowed: true, reason: "可暂停" },
  businessTypeOptions: ["采购固定资产", "采购支出"],
  plan: {
    revision: 1,
    enabled: true,
    times: ["02:00", "14:00"],
    lookbackDays: 90,
    accountMode: "all",
    accountIds: [],
    excludedIds: ["9"],
    businessTypes: ["采购固定资产"],
    nextRunAt: "2026-10-20T06:00:00Z",
  },
};
const render = (component, props) =>
  renderToStaticMarkup(createElement(MemoryRouter, null, createElement(component, props)));
test("全部账套的排除语义和新增自动纳入明确", () => {
  const html = render(Scope, {
    value: data.plan,
    change() {},
    query() {},
    disabled: false,
    accounts: [{ asid: "9", name: "测试账套" }],
  });
  assert.match(html, /新增账套自动纳入/);
  assert.match(html, /已排除/);
  assert.match(html, /type="checkbox" checked=""/);
});
test("定时计划按北京时间展示，保存与暂停有明确操作", () => {
  const html = render(Plan, { data, accounts: null, busy: false, query() {}, save() {} });
  assert.match(html, /14:00/);
  assert.match(html, /保存同步计划/);
  assert.match(html, /暂停已保存计划/);
  assert.match(html, /请用手动补拉/);
});
test("未授权不能提交，等待任务详情时不显示伪成功", () => {
  const html = render(Batch, {
    data: { ...data, submit: { allowed: false, reason: "未绑定" } },
    accounts: null,
    busy: false,
    query() {},
    submit() {},
  });
  assert.match(html, /disabled=""[^>]*>提交后台拉取/);
  assert.match(render(Detail, {}), /正在读取任务详情/);
});
test("后台提交失败只请求一次，并保持调用方请求编号", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return Response.json({ error: "请查询原任务" }, { status: 503 });
  });
  const body = {
    requestId: "original-id",
    startDate: "2026-10-01",
    endDate: "2026-10-19",
    accountMode: "all",
    accountIds: [],
    excludedIds: [],
    businessTypes: ["采购支出"],
  };
  await assert.rejects(api.submitSyncBatch(body), /查询原任务/);
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].body, body);
});
test("计划更新不回传服务端下次时间，保留版本和用户配置", async (t) => {
  let captured;
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    captured = JSON.parse(options.body);
    return Response.json(data);
  });
  await api.saveSyncPlan(data.plan);
  assert.equal(captured.revision, 1);
  assert.equal(captured.nextRunAt, undefined);
  assert.deepEqual(captured.times, ["02:00", "14:00"]);
});
