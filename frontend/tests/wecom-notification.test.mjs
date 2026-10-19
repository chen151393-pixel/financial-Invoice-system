import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
import { MemoryRouter } from "react-router";

let server, api, Panel, TaskPanel;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  api = await server.ssrLoadModule("/src/modules/task/api/delivery.ts");
  ({ WecomNotification: Panel } = await server.ssrLoadModule(
    "/src/modules/task/components/WecomNotification.tsx",
  ));
  ({ TaskNotification: TaskPanel } = await server.ssrLoadModule(
    "/src/modules/task/components/TaskNotification.tsx",
  ));
});
after(async () => {
  await server?.close();
});

test("提交只传版本和摘要，失败不重放，也不传任意群或路径", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return Response.json({ error: "结果待核实" }, { status: 409 });
  });
  await assert.rejects(
    api.submitDelivery(
      "12",
      {
        revision: 1,
        groupRevision: 2,
        snapshotSha256: "digest",
        chatId: "must-not-send",
        files: [{ path: "private" }],
      },
      "request-id",
    ),
    /结果待核实/,
  );
  assert.deepEqual(calls, [
    {
      url: "/api/tasks/12/notification/submit",
      body: {
        revision: 1,
        groupRevision: 2,
        snapshotSha256: "digest",
        requestId: "request-id",
      },
    },
  ]);
});

test("待确认不是已发送，未知结果展示核实而非重发", () => {
  const item = {
    id: "1",
    revision: 1,
    statusLabel: "结果待核实，禁止重复提交",
    corpId: "corp",
    chatId: "wr001",
    groupName: "测试供应商群",
    employee: "张三",
    userid: "buyer",
    files: [],
    createdAt: "2026-10-19T01:00:00Z",
    submittedAt: null,
    lastCheckedAt: null,
    sentAt: null,
    msgid: "",
    message: "请开票",
    error: "创建请求超时",
    refresh: { allowed: true },
    reconcile: { allowed: true },
  };
  const html = renderToStaticMarkup(
    createElement(Panel, {
      controller: { items: [item], loading: false, busy: false, error: "", preview: null, candidates: null },
    }),
  );
  for (const label of ["核实发送记录", "结果待核实", "创建请求超时", "尚无成功回执", "群主在企微确认"])
    assert.ok(html.includes(label));
  const actions = html.match(/aria-label="发送记录操作"[^>]*>(.*?)<\/div>/s)?.[1];
  assert.ok(actions);
  for (const label of ["刷新发送结果", "核实发送记录", "重新读取记录"]) assert.ok(actions.includes(label));
  assert.ok(!html.includes("提交企微群发"));
  assert.ok(!html.includes("自动发送（未接入）"));
});

const notification = {
  revision: 1,
  groupName: "测试群",
  employee: "张三",
  message: "请开票",
  defaultMessage: "请开票",
  statusLabel: "待通知",
  groupConfigReason: "已绑定默认群",
  supplierGroup: { revision: 2, groupName: "测试群", chatId: "wr001", employee: "张三", userid: "buyer" },
  edit: { allowed: true, reason: "可编辑" },
  record: { allowed: true, reason: "在企微实际发送后登记。" },
  send: { allowed: false, reason: "存在未决通知" },
  history: [],
};
const controller = { items: [], loading: false, busy: false, error: "", preview: null, candidates: null };

test("群发入口紧随保存及人工操作，保留后端禁用条件", () => {
  for (const allowed of [false, true]) {
    const html = renderToStaticMarkup(
      createElement(
        MemoryRouter,
        null,
        createElement(TaskPanel, {
          detail: {
            task: { supplier: "测试供应商", company: "测试公司" },
            documents: [],
            notification: {
              ...notification,
              send: { allowed, reason: allowed ? "可提交" : "存在未决通知" },
            },
          },
          delivery: controller,
        }),
      ),
    );
    const actions = html.match(/aria-label="通知操作"[^>]*>(.*?)<\/div>/s)?.[1];
    assert.ok(actions);
    const labels = [...actions.matchAll(/<button[^>]*>(.*?)<\/button>/g)].map((match) => match[1]);
    assert.deepEqual(labels, ["保存通知", "登记已人工发送", "提交企微群发"]);
    assert.match(
      html,
      /class="task-notification-message">[\s\S]*?<textarea[\s\S]*?aria-label="复制通知正文"/,
    );
    assert.equal((html.match(/aria-label="复制通知正文"/g) || []).length, 1);
    assert.equal((html.match(/>提交企微群发</g) || []).length, 1);
    assert.equal(/disabled=""[^>]*>提交企微群发/.test(actions), !allowed);
    assert.ok(html.includes(allowed ? "可提交" : "存在未决通知"));
  }
});

test("发送记录加载、空结果和失败时仍有读取入口", () => {
  for (const state of [
    { loading: true, label: "正在读取发送记录…" },
    { label: "暂无企微提交记录。" },
    { error: "读取失败，请重试", label: "读取失败，请重试" },
  ]) {
    const html = renderToStaticMarkup(createElement(Panel, { controller: { ...controller, ...state } }));
    assert.ok(html.includes(state.label));
    assert.ok(html.includes("重新读取记录"));
    assert.equal(/disabled=""[^>]*>重新读取记录/.test(html), !!state.loading);
    if (state.error) assert.match(html, /role="alert"/);
  }
});
