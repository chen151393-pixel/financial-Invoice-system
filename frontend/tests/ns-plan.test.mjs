import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { createServer } from "vite";

let server, Form, Detail, Cards, Status, Tabs, Records, DetailContent, api;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  ({ NsPlanForm: Form } = await server.ssrLoadModule("/src/modules/sync/components/NsPlanForm.tsx"));
  ({ NsPlanBatchPage: Detail } = await server.ssrLoadModule("/src/modules/sync/pages/NsPlanBatchPage.tsx"));
  ({ NsBatchDetailContent: DetailContent } = await server.ssrLoadModule(
    "/src/modules/sync/pages/NsPlanBatchPage.tsx",
  ));
  ({ NsBatchRecords: Records } = await server.ssrLoadModule(
    "/src/modules/sync/components/NsPlanBatches.tsx",
  ));
  ({ SyncSourceCards: Cards } = await server.ssrLoadModule(
    "/src/modules/sync/components/SyncSourceCards.tsx",
  ));
  ({ NsSyncStatus: Status } = await server.ssrLoadModule("/src/modules/sync/components/NsSyncStatus.tsx"));
  ({ SyncTabs: Tabs } = await server.ssrLoadModule("/src/modules/sync/components/SyncTabs.tsx"));
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

const record = {
  requestId: "manual-request",
  recordType: "manual",
  kind: "customs-declarations",
  kindLabel: "报关单",
  phase: "partial",
  label: "部分成功",
  trigger: "manual",
  startDate: "2026-08-01",
  endDate: "2026-08-31",
  createdAt: "2026-10-30T08:00:00Z",
  finishedAt: "2026-10-30T08:01:00Z",
  message: "已保存 1 张，失败 1 张",
  fetched: 2,
  created: 1,
  updated: 0,
  failed: 1,
};
const historyState = {
  data: { items: [record], counts: { partial: 1 }, total: 1, pages: 1, page: 1, pageSize: 20, plan: null },
  phase: "",
  error: "",
  refresh() {},
  change() {},
};

test("NS 记录展示手动与计划、后端数量、日期范围和独立详情入口", () => {
  const scheduled = {
    ...record,
    recordType: "plan",
    requestId: "plan-request",
    trigger: "schedule",
    kindLabel: "子采购单",
  };
  const html = render(Records, {
    state: { ...historyState, data: { ...historyState.data, items: [record, scheduled] } },
  });
  assert.match(html, /NS 同步执行记录/);
  assert.match(html, /手动提交/);
  assert.match(html, /定时计划/);
  assert.match(html, /2026-08-01 至 2026-08-31/);
  assert.match(html, /失败单据/);
  assert.match(html, /manual-request\?recordType=manual/);
  assert.match(html, /href="\/sync\/ns\/batches\/plan-request"/);
  assert.match(html, /任务状态/);
  assert.doesNotMatch(html, /查询账套/);
});

test("NS 记录区覆盖初始加载、错误重试、空结果与过期数据提示", () => {
  assert.match(render(Records, { state: { ...historyState, data: null } }), /正在读取执行记录/);
  const failed = render(Records, { state: { ...historyState, data: null, error: "服务暂时不可用" } });
  assert.match(failed, /执行记录读取失败[\s\S]*重新读取/);
  assert.match(
    render(Records, { state: { ...historyState, error: "服务暂时不可用" } }),
    /记录可能不是最新状态/,
  );
  assert.match(
    render(Records, { state: { ...historyState, data: { ...historyState.data, items: [] } } }),
    /当前条件下没有 NS 执行记录/,
  );
});

test("手动待核实详情展示失败单据且不会声称定时计划自动暂停", () => {
  const detail = {
    ...record,
    phase: "unknown",
    label: "结果待核实",
    poll: false,
    pages: [
      {
        index: 2,
        requestId: record.requestId,
        status: "interrupted",
        statusLabel: "已中断",
        count: 2,
        saved: 1,
        failed: 1,
        skipped: 0,
        unknown: 0,
        error: null,
        progress: null,
        failures: [
          { id: "1", number: "CD000727", status: "failed", reason: "NS 同规则查询失败（HTTP 404）" },
        ],
      },
    ],
  };
  const html = render(DetailContent, { state: { data: detail, error: "", refresh() {} } });
  assert.match(html, /第 2 页/);
  assert.match(html, /CD000727[\s\S]*HTTP 404/);
  assert.match(html, /请勿直接重复提交/);
  assert.doesNotMatch(html, /定时计划已自动暂停|重新启用计划|原游标重新排队/);
});

test("NS 状态筛选传给后端，详情携带记录类型避免相同编号串记录", async (t) => {
  const urls = [];
  t.mock.method(globalThis, "fetch", async (url) => {
    urls.push(String(url));
    return Response.json({});
  });
  await api.listNsBatches(2, "unknown");
  await api.getNsBatch("shared-id", "manual");
  await api.getNsBatch("shared-id");
  assert.match(urls[0], /page=2&pageSize=20&phase=unknown/);
  assert.match(urls[1], /shared-id\?recordType=manual$/);
  assert.match(urls[2], /shared-id\?recordType=plan$/);
});

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
test("自动暂停原因显示在保存按钮旁", () => {
  const paused = {
    ...data,
    plan: { ...data.plan, enabled: false, pausedReason: "存在结果待核实的分页，计划已自动暂停" },
  };
  const html = render(Form, { data: paused, busy: false, save() {} });
  assert.match(html, /role="status"[^>]*>存在结果待核实的分页[\s\S]*保存同步计划/);
});
test("状态条与柠檬云同样三格：可否启用、计划状态与下次执行", () => {
  const html = render(Status, { data });
  assert.match(html, /定时同步[\s\S]*可启用/);
  assert.match(html, /定时计划[\s\S]*已启用[\s\S]*每日 02:00、14:00/);
  assert.match(html, /下次执行/);
  const paused = { ...data, plan: { ...data.plan, enabled: false, pausedReason: "已自动暂停" } };
  assert.match(render(Status, { data: paused }), /已自动暂停，原因见定时计划/);
});
test("NS 与柠檬云共用“手动补拉 / 定时计划”页签，处理中禁止切换", () => {
  const html = renderToStaticMarkup(createElement(Tabs, { value: "plan", onChange() {}, disabled: true }));
  assert.match(html, /disabled=""[^>]*>手动补拉/);
  assert.match(html, /aria-pressed="true"[^>]*>定时计划/);
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
