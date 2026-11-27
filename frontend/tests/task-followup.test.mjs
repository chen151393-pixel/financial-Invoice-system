import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter as Router } from "react-router";
import { createServer } from "vite";

let server, BoardTaskItem, BoardSearch, TaskOverview, TaskHistory, boardQuery, boardApi, taskApi, money;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  boardApi = await server.ssrLoadModule("/src/modules/task/api/board.ts");
  taskApi = await server.ssrLoadModule("/src/modules/task/api/task.ts");
  boardQuery = await server.ssrLoadModule("/src/modules/task/hooks/board-query.ts");
  ({ BoardSearch } = await server.ssrLoadModule("/src/modules/task/components/BoardSearch.tsx"));
  ({ money } = await server.ssrLoadModule("/src/shared/format/money.ts"));
  ({ BoardTaskItem } = await server.ssrLoadModule("/src/modules/task/components/BoardTaskItem.tsx"));
  ({ TaskOverview } = await server.ssrLoadModule("/src/modules/task/components/TaskOverview.tsx"));
  ({ TaskHistory } = await server.ssrLoadModule("/src/modules/task/components/TaskHistory.tsx"));
});
after(async () => {
  await server?.close();
});

test("流转记录保留后端顺序和步骤号，最早审核为第1步，操作人展示姓名", () => {
  const history = [
    {
      id: "document:7:1",
      sequence: 4,
      kind: "document",
      label: "获取子采购合同：较新合同",
      at: "2026-10-30T10:30:00+08:00",
      archivedAt: "2026-10-30T10:31:00+08:00",
      archivePath: "/share/较新合同.pdf",
      environment: "prod",
      nsId: "501",
      sha256: "digest",
    },
    {
      id: "event:2",
      sequence: 3,
      kind: "event",
      label: "最近通知",
      at: "2026-10-30T02:00:00Z",
      actor: "user:fs:11gc6fb6",
      actorName: "测试财务人员",
      reason: "CD002",
    },
    {
      id: "document:8:2",
      sequence: 2,
      kind: "document",
      label: "获取子采购合同：中间合同",
      at: "2026-10-25T10:00:00+08:00",
    },
    {
      id: "event:1",
      sequence: 1,
      kind: "event",
      label: "最早审核",
      at: "2026-10-20T10:30:05+08:00",
      actor: "system",
      actorName: "系统",
      reason: "CD001",
    },
  ];
  // 历史字段保留兼容，但前端不能重新排列或编号。
  const detail = { task: { id: "7" }, events: [], documents: [], history };
  const original = structuredClone(detail);
  const html = renderToStaticMarkup(createElement(TaskHistory, { detail }));
  assert.deepEqual(
    [...html.matchAll(/<strong>(.*?)<\/strong>/g)].map((match) => match[1]),
    ["获取子采购合同：较新合同", "最近通知", "获取子采购合同：中间合同", "最早审核"],
  );
  assert.match(html, /<ol[^>]*reversed=""[^>]*aria-label="流转记录，最新操作在前"/);
  assert.deepEqual(
    [...html.matchAll(/<li value="(\d+)"/g)].map((match) => Number(match[1])),
    [4, 3, 2, 1],
  );
  assert.match(html, /操作人 <span title="system">系统<\/span>/);
  assert.match(html, /操作人 <span title="user:fs:11gc6fb6">测试财务人员<\/span>/);
  assert.match(html, /CD001/);
  assert.match(html, /CD002/);
  assert.match(html, /保存到共享盘/);
  assert.match(html, /文件 SHA-256：digest/);
  assert.doesNotMatch(html, /未下载合同/);
  assert.deepEqual(detail, original);
  assert.match(
    renderToStaticMarkup(
      createElement(TaskHistory, { detail: { task: { id: "7" }, events: [], documents: [], history: [] } }),
    ),
    /任务编号：7/,
  );
});

test("同刻流转记录按后端步骤显示，补存成功不会被显示为退回待保存", () => {
  const records = [
    {
      id: "event:9007199254740995",
      sequence: 3,
      kind: "event",
      at: "2026-11-26T06:14:31.123456Z",
      label: "子采购合同已全部保存到共享盘",
      actor: "maintenance:contract-recovery",
      actorName: "maintenance:contract-recovery",
      reason: "CD000953：合同批量补存完成",
    },
    {
      id: "event:9007199254740994",
      sequence: 2,
      kind: "event",
      at: "2026-11-26T06:14:31.123456Z",
      label: "子采购合同补存成功",
      actor: "maintenance:contract-recovery",
      actorName: "maintenance:contract-recovery",
      reason: "CD000953：定向补存子采购合同",
    },
    {
      id: "event:1",
      sequence: 1,
      kind: "event",
      at: "2026-11-26T03:47:40Z",
      label: "财务审核通过，生成开票任务",
      actor: "system",
      actorName: "系统",
      reason: "",
    },
  ];
  const html = renderToStaticMarkup(
    createElement(TaskHistory, { detail: { task: { id: "481" }, history: records } }),
  );
  assert.deepEqual(
    [...html.matchAll(/<strong>(.*?)<\/strong>/g)].map((match) => match[1]),
    records.map((record) => record.label),
  );
  assert.deepEqual(
    [...html.matchAll(/<li value="(\d+)"/g)].map((match) => Number(match[1])),
    [3, 2, 1],
  );
  assert.doesNotMatch(html, /待保存子采购合同/);
});

test("供应商详情使用独立接口，保存固定范围版本和幂等编号；失败不自动重放", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, body: options.body ? JSON.parse(options.body) : null });
    return Response.json({ error: "范围已变化" }, { status: 409 });
  });
  await assert.rejects(taskApi.getSupplierTask("18", true), /范围已变化/);
  await assert.rejects(
    taskApi.saveSupplierTaskNotification(
      "18",
      { revision: 3, groupName: "开票群", employee: "张三", message: "全部子采购合同" },
      "a".repeat(64),
    ),
    /范围已变化/,
  );
  assert.equal(calls.length, 2);
  assert.equal(calls[0].url, "/api/task/supplier-tasks/18?completed=true");
  assert.equal(calls[1].url, "/api/task/supplier-tasks/18/notification/draft");
  assert.equal(calls[1].body.scopeRevision, "a".repeat(64));
  assert.match(calls[1].body.requestId, /^[0-9a-f-]{36}$/);
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
    groupBy: "supplier",
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
  assert.doesNotMatch(html, /收起流程|展开流程|查看全部资料|生成通知/);
  // 「跟进详情」直接进入任务当前节点，不再带分区锚点，也不放「查看合同」等节点按钮
  assert.match(html, /href="\/tasks\/1"/);
  assert.doesNotMatch(html, /#task-|查看合同|去通知供应商/);
  assert.equal((html.match(/aria-label="隔离测试供应商 CD001 跟进详情"/g) || []).length, 1);
  assert.match(html, /ui-stepper/);
  assert.match(html, /CD001/);
  assert.doesNotMatch(html, /SUB001|子采购 /);
  assert.doesNotMatch(html, /重新审核后继续|下一步/);
  assert.doesNotMatch(html, /class="ui-card /);
});

test("任务概览汇总合同份数，完整子采购单号留在合同区", () => {
  const html = renderToStaticMarkup(
    createElement(TaskOverview, {
      detail: { task: { ...task, orderNumbers: ["SUB001", "SUB002"], reviewRevision: 1 }, steps: [] },
      section: "documents",
      onNavigate() {},
    }),
  );
  assert.match(html, /2 份子采购合同/);
  assert.match(html, /测试采购公司/);
  assert.doesNotMatch(html, /SUB001|SUB002/);
});

test("报关单分开模式以 CD 与真实报关单号为主标题，缺号时明确提示", () => {
  const render = (declarationNumber) =>
    renderToStaticMarkup(
      createElement(
        Router,
        null,
        createElement(BoardTaskItem, {
          item: {
            task: { ...task, declarationNumber },
            grouped: false,
            currentNode: "notification",
            currentLabel: "待通知供应商",
            steps: [],
            blockedReason: "",
          },
        }),
      ),
    );
  const html = render("123456789012345678");
  assert.match(html, /<h3[^>]*><a[^>]*>CD001 · 123456789012345678<\/a><\/h3>/);
  assert.match(html, /class="tb-item__meta"><span>隔离测试供应商<\/span>/);
  assert.match(render(""), /CD001 · 真实报关单号待补充/);
});

test("供应商合并任务进入独立详情路由，报关单模式写入查询地址", () => {
  const html = renderToStaticMarkup(
    createElement(
      Router,
      null,
      createElement(BoardTaskItem, {
        item: {
          grouped: true,
          taskIds: ["1", "2"],
          task,
          currentNode: "notification",
          currentLabel: "待通知供应商",
          missing: [],
          blockedReason: "",
          nextAction: "",
          steps: [{ key: "notification", label: "通知供应商", state: "current" }],
          notifyRecord: { allowed: true, reason: "" },
        },
      }),
    ),
  );
  assert.match(html, /href="\/tasks\/supplier\/1"/);
  assert.match(html, /<h3[^>]*><a[^>]*>隔离测试供应商<\/a><\/h3>/);
  assert.doesNotMatch(html, /收起流程|生成通知/);
  const query = boardQuery.readBoardQuery(new URLSearchParams("groupBy=declaration"));
  assert.equal(query.groupBy, "declaration");
  assert.equal(boardQuery.writeBoardQuery(query).get("groupBy"), "declaration");
  assert.equal(boardQuery.readBoardQuery(new URLSearchParams()).groupBy, "supplier");
});

test("批量登记提交组锚点、确认范围版本与通知日期，不由前端展开任务", async (t) => {
  const taskApi = await server.ssrLoadModule("/src/modules/task/api/task.ts");
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, method: options.method, body: JSON.parse(options.body) });
    return Response.json({
      groups: [{ id: "1", status: "recorded", taskIds: ["1", "2"], reason: "" }],
      recordedGroups: 1,
      recordedTasks: 2,
      skippedGroups: 0,
      unknownGroups: 0,
    });
  });
  const groups = [{ id: "1", scopeRevision: "a".repeat(64) }];
  const result = await taskApi.recordNotificationGroups("supplier", groups, "电话已通知", "2026-11-18");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/tasks/notification/record-groups");
  assert.equal(calls[0].method, "POST");
  assert.deepEqual(calls[0].body, {
    groupBy: "supplier",
    groups,
    note: "电话已通知",
    notifiedOn: "2026-11-18",
  });
  assert.equal(result.recordedTasks, 2);
});

test("任务卡片仅在进入批量模式且后端允许登记时显示勾选框", () => {
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
  const render = (allowed, checked = false, selecting = true) =>
    renderToStaticMarkup(
      createElement(
        Router,
        null,
        createElement(BoardTaskItem, {
          item: item(allowed),
          selection: selecting ? { checked, disabled: false, onToggle() {} } : undefined,
        }),
      ),
    );
  assert.match(
    render(true),
    /type="checkbox"[^>]*aria-label="选择 隔离测试供应商 CD001，用于批量登记已通知"/,
  );
  assert.match(render(true, true), /type="checkbox"[^>]*checked=""/);
  assert.doesNotMatch(render(false), /type="checkbox"/);
  assert.doesNotMatch(render(true, false, false), /type="checkbox"/);
});

test("批量登记弹窗默认北京时间今天，可选择日期，并展示逐组结果", async (t) => {
  t.mock.timers.enable({ apis: ["Date"], now: Date.parse("2026-11-18T17:00:00Z") });
  const { NotifyBatchDialog } = await server.ssrLoadModule(
    "/src/modules/task/components/NotifyBatchDialog.tsx",
  );
  const items = ["1", "2"].map((id) => ({
    id,
    scopeRevision: "a".repeat(64),
    targets: [
      { id, supplier: `供应商${id}`, recordNumber: task.recordNumber, orderNumbers: task.orderNumbers },
    ],
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
  for (const value of [
    "本页已选 2",
    "通知日期（北京时间）",
    "系统不会发送任何消息",
    "确认已通知 2 组（2 个任务）",
    "SUB001",
    "已通知任务不在本次范围",
  ])
    assert.ok(confirm.includes(value), value);
  assert.match(confirm, /type="date"[^>]*required=""[^>]*value="2026-11-19"/);
  assert.doesNotMatch(confirm, /通知时间记为今天/);
  const done = render({
    result: {
      groups: [
        { id: "1", status: "recorded", taskIds: ["1"], reason: "本组全部登记" },
        { id: "2", status: "skipped", taskIds: [], reason: "范围已变化，请刷新" },
      ],
      recordedGroups: 1,
      recordedTasks: 1,
      skippedGroups: 1,
      unknownGroups: 0,
    },
  });
  for (const value of [
    "已登记 1 组（1 个任务），跳过 1 组",
    "范围已变化，请刷新",
    "整组已登记",
    "整组跳过",
    "关闭",
  ])
    assert.ok(done.includes(value), value);
  assert.doesNotMatch(done, /确认已通知/);
  assert.doesNotMatch(done, /type="date"/);
  assert.match(render({ busy: true }), /type="date"[^>]*disabled=""/);
  assert.ok(render({ error: "请求失败；请核实" }).includes("请求失败；请核实"));
});

test("发票比对收票概况展示后端金额和各报关单，通知入口保持可操作", async () => {
  const { TaskReceiptCard } = await server.ssrLoadModule("/src/modules/task/components/TaskReceiptCard.tsx");
  const summary = {
    id: "7",
    recordNumber: "CD000995",
    currency: "CNY",
    statusLabel: "等待开票",
    orderNumbers: ["YE-JH20260821-P281-2", "YE-JH20260924-P358-1"],
    expectedAmount: "125820",
    receivedAmount: "20.125",
    outstandingAmount: "125800",
  };
  const detail = {
    grouped: true,
    task: { ...summary, expectedAmount: "330588", receivedAmount: "20.125", outstandingAmount: "330580" },
    memberTasks: [
      summary,
      {
        ...summary,
        id: "8",
        recordNumber: "CD001000",
        orderNumbers: ["SUB-201"],
        expectedAmount: "114048",
        receivedAmount: "0",
      },
    ],
  };
  const before = structuredClone(detail);
  let notified = false;
  const tree = TaskReceiptCard({
    detail,
    onNotification() {
      notified = true;
    },
  });
  tree.props.children[0].props.actions.props.onClick();
  assert.equal(notified, true);
  const html = renderToStaticMarkup(tree);
  assert.match(html, /收票概况/);
  assert.match(html, /查看通知与催票/);
  assert.match(html, /应开合计[\s\S]*330,588\.00 CNY/);
  assert.match(html, /已收金额[\s\S]*20\.125 CNY/);
  // 待收直接使用后端值，不能在浏览器用应开减已收重新计算。
  assert.match(html, /待收金额[\s\S]*330,580\.00 CNY/);
  assert.match(html, /CD000995[\s\S]*YE-JH20260821-P281-2、YE-JH20260924-P358-1/);
  assert.match(html, /CD001000[\s\S]*SUB-201[\s\S]*114,048\.00 CNY[\s\S]*0\.00 CNY/);
  assert.deepEqual(detail, before);
});

test("收票概况兼容单任务和缺失金额，不用零填补未知金额", async () => {
  const { TaskReceiptCard } = await server.ssrLoadModule("/src/modules/task/components/TaskReceiptCard.tsx");
  const task = {
    id: "9",
    recordNumber: "CD000953",
    orderNumbers: [],
    currency: "USD",
    statusLabel: "待核实",
    expectedAmount: null,
    outstandingAmount: null,
  };
  const html = renderToStaticMarkup(
    createElement(TaskReceiptCard, { detail: { task }, onNotification() {} }),
  );
  assert.match(html, /CD000953/);
  assert.match(html, /子采购单号待补充/);
  assert.match(html, /金额待确认/);
  assert.doesNotMatch(html, /0\.00 USD/);
  const empty = renderToStaticMarkup(
    createElement(TaskReceiptCard, { detail: { task, grouped: true, memberTasks: [] }, onNotification() {} }),
  );
  assert.match(empty, /暂无报关单收票明细/);
});
