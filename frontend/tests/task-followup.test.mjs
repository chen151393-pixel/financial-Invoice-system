import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter as Router } from "react-router";
import { createServer } from "vite";

let server, BoardTaskItem, boardApi, money;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  boardApi = await server.ssrLoadModule("/src/modules/task/api/board.ts");
  ({ money } = await server.ssrLoadModule("/src/shared/format/money.ts"));
  ({ BoardTaskItem } = await server.ssrLoadModule("/src/modules/task/components/BoardTaskItem.tsx"));
});
after(async () => {
  await server?.close();
});

test("跟进查询保留工作台范围，日期为空交给后端按不限处理", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return Response.json({ error: "测试错误" }, { status: 503 });
  });
  await assert.rejects(
    boardApi.queryTaskBoard({
      keyword: "",
      supplierId: "7",
      node: "",
      stage: "documents",
      createdFrom: "",
      createdTo: "",
      page: 1,
      pageSize: 20,
    }),
    /测试错误/,
  );
  assert.equal(calls[0].url, "/api/tasks/board/query");
  assert.equal(calls[0].body.stage, "documents");
  assert.equal(calls[0].body.supplierId, "7");
  assert.equal(calls[0].body.createdFrom, null);
  assert.equal(calls[0].body.createdTo, null);
});

test("任务金额格式化保留零值、高精度与未知值", () => {
  assert.equal(money("0"), "0.00");
  assert.equal(money("999999999999999999.123456"), "999,999,999,999,999,999.123456");
  for (const value of [undefined, null, ""]) assert.equal(money(value), "—");
});

const task = {
  id: "1",
  supplier: "隔离测试供应商",
  company: "测试采购公司",
  currency: "CNY",
  recordNumber: "CD001",
  orderNumbers: ["SUB001"],
  status: "partially_received",
  statusLabel: "部分收票",
  reason: "等待其余发票",
  outstandingAmount: "104000.000001",
  receiptPercent: "42.2",
  receiptBarPercent: "42.2",
  followupEmployee: "张采购",
  lastContactAt: "2026-10-09T08:20:00Z",
  waitingLabel: "已等待 18 天",
};

test("采购任务行默认展开流程，展示下一步、阻塞原因、零金额进度及操作入口", () => {
  const html = renderToStaticMarkup(
    createElement(
      Router,
      null,
      createElement(BoardTaskItem, {
        item: {
          task: { ...task, outstandingAmount: "0", receiptPercent: "0", receiptBarPercent: "0" },
          currentNode: "documents",
          currentLabel: "待存合同",
          blockedReason: "来源已变化，请财务重新审核",
          nextAction: "重新审核后继续",
          steps: [{ key: "documents", label: "资料准备", state: "current" }],
        },
      }),
    ),
  );
  for (const value of ["隔离测试供应商", "待存合同", "来源已变化，请财务重新审核", "0.00", "0%"])
    assert.ok(html.includes(value), value);
  assert.match(html, /aria-expanded="true"/);
  assert.match(html, /aria-controls="[^"]+"/);
  assert.match(html, /href="\/tasks\/1#task-documents"/);
  assert.match(html, /href="\/tasks\/1"/);
  assert.match(html, /ui-stepper/);
  assert.match(html, /重新审核后继续/);
  assert.doesNotMatch(html, /class="ui-card /);
});
