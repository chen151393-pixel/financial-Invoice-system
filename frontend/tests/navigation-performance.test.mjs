import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { createServer } from "vite";

let server,
  matching,
  task,
  board,
  workbench,
  review,
  invoices,
  source,
  sync,
  WorkspaceLoading,
  SessionContext;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  matching = await server.ssrLoadModule("/src/modules/matching/api/index.ts");
  workbench = await server.ssrLoadModule("/src/modules/matching/api/workbench-api.ts");
  task = await server.ssrLoadModule("/src/modules/task/api/task.ts");
  board = await server.ssrLoadModule("/src/modules/task/api/board.ts");
  review = await server.ssrLoadModule("/src/modules/review/api.ts");
  invoices = await server.ssrLoadModule("/src/modules/invoice/api/invoice.ts");
  source = await server.ssrLoadModule("/src/modules/source/api.ts");
  sync = await server.ssrLoadModule("/src/modules/sync/api.ts");
  ({ WorkspaceLoading } = await server.ssrLoadModule("/src/app/WorkspaceLoading.tsx"));
  ({ SessionContext } = await server.ssrLoadModule("/src/modules/identity/session-context.ts"));
});
after(async () => {
  await server?.close();
});

test("导航读取直接发业务请求并传递取消信号，401 不重复检查会话或重放", async (t) => {
  const requests = [];
  let status = 200;
  t.mock.method(globalThis, "fetch", async (url, options) => {
    requests.push({ url, options });
    return Response.json(status === 200 ? {} : { error: "请先登录" }, { status });
  });
  const controller = new AbortController();
  for (const read of [
    () => matching.getMatchingQueue({}, controller.signal),
    () => matching.getInvoiceMatching("1", controller.signal),
    () => matching.queryInvoiceMatchList({}, controller.signal),
    () => matching.getInvoiceTotals({}, controller.signal),
    () => workbench.queryWorkbench({}, controller.signal),
    () => task.getTask("1", controller.signal),
    () => task.getSupplierTask("1", false, controller.signal),
    () => board.queryTaskBoard({}, controller.signal),
    () => review.queryDeclarations({}, controller.signal),
    () => invoices.getInvoiceStats(new URLSearchParams(), controller.signal),
    () => invoices.getImportConfiguration(controller.signal),
    () => source.queryPlSourceComparison({}, controller.signal),
    () => sync.getSources(controller.signal),
  ]) {
    requests.length = 0;
    await read();
    assert.equal(requests.length, 1);
    assert.notEqual(requests[0].url, "/api/session");
    assert.equal(requests[0].options.signal, controller.signal);
  }
  status = 401;
  requests.length = 0;
  await assert.rejects(matching.getInvoiceMatching("1"), { message: "请先登录", status: 401 });
  assert.equal(requests.length, 1);
});

test("页面代码加载时保留授权菜单、当前页面和读屏提示", () => {
  const html = renderToStaticMarkup(
    createElement(
      MemoryRouter,
      null,
      createElement(
        SessionContext,
        {
          value: {
            phase: "ready",
            user: { name: "测试财务", roles: [], pages: ["invoice-followup", "finance"] },
            signOut: async () => {},
          },
        },
        createElement(WorkspaceLoading, { view: "invoice-followup", label: "开票跟进" }),
      ),
    ),
  );
  assert.match(html, /<main/);
  assert.match(html, /<h1>开票跟进<\/h1>/);
  assert.match(html, /aria-label="正在加载开票跟进…"/);
  assert.match(html, /财务核对/);
  assert.doesNotMatch(html, /供应商档案|数据同步/);
  assert.match(html, /aria-current="page"/);
});
