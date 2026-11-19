import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter as Router } from "react-router";
import { createServer } from "vite";

let server, BoardTaskItem, BoardSearch, boardQuery, boardApi, money;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  boardApi = await server.ssrLoadModule("/src/modules/task/api/board.ts");
  boardQuery = await server.ssrLoadModule("/src/modules/task/hooks/board-query.ts");
  ({ BoardSearch } = await server.ssrLoadModule("/src/modules/task/components/BoardSearch.tsx"));
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
      supplierName: "供应商甲",
      recordNo: "CD100",
      purchaseOrderNo: "SUB-200",
      node: "",
      stage: "documents",
      createdFrom: "",
      createdTo: "",
      page: 1,
      pageSize: 20,
    }),
    /测试错误/,
  );
  assert.equal(calls[0].url, "/api/task/board/query");
  assert.equal(calls[0].body.supplierName, "供应商甲");
  assert.equal(calls[0].body.recordNo, "CD100");
  assert.equal(calls[0].body.purchaseOrderNo, "SUB-200");
  assert.equal(calls[0].body.stage, "documents");
  assert.equal(calls[0].body.supplierId, "7");
  assert.equal(calls[0].body.createdFrom, null);
  assert.equal(calls[0].body.createdTo, null);
});

test("组合查询地址保留中文、特殊字符、节点与分页，清空条件不残留旧参数", () => {
  const query = {
    keyword: "",
    supplierId: "",
    supplierName: "甲&乙",
    recordNo: "CD100",
    purchaseOrderNo: "SUB/200",
    node: "done",
    page: 3,
    pageSize: 10,
  };
  assert.deepEqual(boardQuery.readBoardQuery(boardQuery.writeBoardQuery(query)), query);
  const cleared = boardQuery.writeBoardQuery({
    ...query,
    supplierName: "",
    recordNo: "",
    purchaseOrderNo: "",
    node: "",
    page: 1,
    pageSize: 20,
  });
  assert.equal(cleared.toString(), "");
});

test("查询栏展示三个独立可访问输入框，加载时禁止重复查询", () => {
  const html = renderToStaticMarkup(
    createElement(BoardSearch, {
      values: { supplierName: "上海", recordNo: "CD870", purchaseOrderNo: "SUB-200" },
      busy: true,
      filtered: true,
      onSearch() {},
      onClear() {},
      onRefresh() {},
    }),
  );
  for (const name of ["supplierName", "recordNo", "purchaseOrderNo"])
    assert.match(html, new RegExp(`name="${name}"`));
  assert.equal((html.match(/<label/g) || []).length, 3);
  assert.equal((html.match(/disabled=""/g) || []).length, 3);
  assert.match(html, /查询中/);
  assert.doesNotMatch(html, /<select/);
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

test("任务卡片默认展开流程，展示阻塞原因、零金额进度；只有跟进详情入口，不放节点按钮和下一步说明", () => {
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
  // 「跟进详情」直接进入任务当前节点，不再带分区锚点，也不放「查看合同」等节点按钮
  assert.match(html, /href="\/tasks\/1"/);
  assert.doesNotMatch(html, /#task-|查看合同|去通知供应商/);
  assert.ok(html.indexOf("收起流程") < html.lastIndexOf("跟进详情"), "跟进详情在最右");
  assert.match(html, /ui-stepper/);
  assert.doesNotMatch(html, /重新审核后继续|下一步/);
  assert.doesNotMatch(html, /class="ui-card /);
});

test("批量登记已通知只提交任务编号与说明，不提交发送时间", async (t) => {
  const taskApi = await server.ssrLoadModule("/src/modules/task/api/task.ts");
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, method: options.method, body: JSON.parse(options.body) });
    return Response.json({ recorded: [{ id: "1", reason: "" }], skipped: [{ id: "2", reason: "已变化" }] });
  });
  const result = await taskApi.recordNotificationBatch(["1", "2"], "电话已通知");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/tasks/notification/record-batch");
  assert.equal(calls[0].method, "POST");
  assert.deepEqual(calls[0].body, { taskIds: ["1", "2"], note: "电话已通知" });
  assert.equal(result.skipped[0].reason, "已变化");
});

test("任务卡片只在后端允许登记时显示勾选框", () => {
  const item = (allowed) => ({
    task,
    currentNode: "notification",
    currentLabel: "待通知供应商",
    blockedReason: "",
    nextAction: "",
    steps: [{ key: "notification", label: "通知供应商", state: "current" }],
    missing: [],
    notifyRecord: { allowed, reason: allowed ? "" : "请先将全部子采购合同保存到共享盘。" },
  });
  const render = (allowed, checked = false) =>
    renderToStaticMarkup(
      createElement(
        Router,
        null,
        createElement(BoardTaskItem, {
          item: item(allowed),
          selection: { checked, disabled: false, onToggle() {} },
        }),
      ),
    );
  assert.match(
    render(true),
    /type="checkbox"[^>]*aria-label="选择 隔离测试供应商 CD001，用于批量登记已通知"/,
  );
  assert.match(render(true, true), /type="checkbox"[^>]*checked=""/);
  assert.doesNotMatch(render(false), /type="checkbox"/);
});

test("批量登记弹窗说明只登记不发送，并展示逐任务结果", async () => {
  const { NotifyBatchDialog } = await server.ssrLoadModule(
    "/src/modules/task/components/NotifyBatchDialog.tsx",
  );
  const items = ["1", "2"].map((id) => ({
    task: { ...task, id, supplier: `供应商${id}` },
    notifyRecord: { allowed: true, reason: "" },
  }));
  const render = (props) =>
    renderToStaticMarkup(
      createElement(NotifyBatchDialog, {
        items,
        busy: false,
        result: null,
        error: "",
        onClose() {},
        onSubmit() {},
        ...props,
      }),
    );
  const confirm = render({});
  for (const value of ["本页已选 2", "通知时间记为今天", "系统不会发送任何消息", "确认已通知 2 个", "SUB001"])
    assert.ok(confirm.includes(value), value);
  const done = render({
    result: {
      recorded: [{ id: "1", reason: "" }],
      skipped: [{ id: "2", reason: "通知已登记发送，无需重复登记。" }],
    },
  });
  for (const value of ["已登记 1 个，跳过 1 个", "通知已登记发送，无需重复登记。", "关闭"])
    assert.ok(done.includes(value), value);
  assert.doesNotMatch(done, /确认已通知/);
  assert.ok(render({ error: "请求失败；请核实" }).includes("请求失败；请核实"));
});
