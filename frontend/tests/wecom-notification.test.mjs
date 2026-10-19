import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

let server, api, Panel;
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
  const notification = {
    revision: 1,
    supplierGroup: { revision: 1 },
    send: { allowed: false, reason: "存在未决通知" },
  };
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
      notification,
      dirty: false,
      disabled: false,
      controller: { items: [item], loading: false, busy: false, error: "", preview: null, candidates: null },
    }),
  );
  for (const label of ["核实发送记录", "结果待核实", "创建请求超时", "尚无成功回执", "群主在企微确认"])
    assert.ok(html.includes(label));
  assert.match(html, /disabled=""[^>]*>提交企微群发/);
  assert.ok(!html.includes("自动发送（未接入）"));
});
