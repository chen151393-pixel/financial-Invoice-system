import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { createServer } from "vite";

let server, Form, Detail, Cards, api;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  ({ NsPlanForm: Form } = await server.ssrLoadModule("/src/modules/sync/components/NsPlanForm.tsx"));
  ({ NsPlanBatchPage: Detail } = await server.ssrLoadModule("/src/modules/sync/pages/NsPlanBatchPage.tsx"));
  ({ SyncSourceCards: Cards } = await server.ssrLoadModule(
    "/src/modules/sync/components/SyncSourceCards.tsx",
  ));
  api = await server.ssrLoadModule("/src/modules/sync/api/ns-plan-api.ts");
});
after(async () => {
  await server?.close();
});
const data = {
  submit: { allowed: true, reason: "可保存并启用 NS 定时同步计划" },
  pause: { allowed: true, reason: "暂停计划不影响已提交批次" },
  coverage: "按 NS 创建日期回扫",
  timezone: "Asia/Shanghai",
  kindOptions: [
    { value: "customs-declarations", label: "报关单", hint: "自动补齐关联子采购单、母采购单" },
    { value: "sub-purchase-orders", label: "子采购单", hint: "补齐其所属报关单" },
  ],
  plan: {
    revision: 2,
    enabled: true,
    nextRunAt: "2026-10-29T18:00:00Z",
    kinds: ["customs-declarations"],
    times: ["02:00", "14:00"],
    lookbackDays: 30,
    pausedReason: null,
  },
};
const render = (component, props) =>
  renderToStaticMarkup(createElement(MemoryRouter, null, createElement(component, props)));

test("NS 计划表单展示单据范围、北京时间时点与更新补齐说明", () => {
  const html = render(Form, { data, busy: false, save() {} });
  assert.match(html, /同步范围/);
  assert.match(html, /type="checkbox" checked=""\/><span>报关单/);
  assert.doesNotMatch(html, /checked=""\/><span>子采购单/);
  assert.match(html, /14:00/);
  assert.match(html, /按 NS 身份更新、补齐/);
  assert.match(html, /暂停已保存计划/);
  assert.match(html, /保存同步计划/);
});
test("后端不允许启用时保存按钮禁用，暂停入口按后端 allowed 显示", () => {
  const blocked = {
    ...data,
    submit: { allowed: false, reason: "NS 账户未配置" },
    pause: { allowed: false, reason: "" },
  };
  const html = render(Form, { data: blocked, busy: false, save() {} });
  assert.match(html, /disabled=""[^>]*>保存同步计划/);
  assert.doesNotMatch(html, /暂停已保存计划/);
});
test("批次详情加载中不显示伪结果", () => {
  assert.match(render(Detail, {}), /正在读取批次详情/);
});
test("同步中心 NS 卡片展示计划状态与下次执行", () => {
  const html = render(Cards, { plan: null, nsPlan: { enabled: true, nextRunAt: "2026-10-29T18:00:00Z" } });
  assert.match(html, /NetSuite[\s\S]*定时计划已启用/);
  assert.doesNotMatch(html, /按需拉取/);
});
test("保存计划只提交可编辑字段，不回传下次时间或暂停原因", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url: String(url), method: options.method, body: JSON.parse(options.body) });
    return Response.json(data);
  });
  await api.saveNsPlan({ ...data.plan, pausedReason: "旧原因" });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].method, "PUT");
  assert.match(calls[0].url, /\/api\/sync\/ns\/plan$/);
  assert.deepEqual(calls[0].body, {
    revision: 2,
    enabled: true,
    kinds: ["customs-declarations"],
    times: ["02:00", "14:00"],
    lookbackDays: 30,
  });
});
