import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { createServer } from "vite";

let server, api, Content, Form, Stats, StateBadge, readTaskQuery, Search, ParentNumbers;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  api = await server.ssrLoadModule("/src/modules/writeback/api.ts");
  ({ TaskContent: Content } = await server.ssrLoadModule(
    "/src/modules/writeback/pages/WritebackRequestPage.tsx",
  ));
  ({ PlanForm: Form } = await server.ssrLoadModule("/src/modules/writeback/components/PlanForm.tsx"));
  ({ WritebackStats: Stats } = await server.ssrLoadModule(
    "/src/modules/writeback/components/WritebackStats.tsx",
  ));
  ({ WritebackStateBadge: StateBadge } = await server.ssrLoadModule(
    "/src/modules/writeback/components/WritebackStateBadge.tsx",
  ));
  ({ readTaskQuery } = await server.ssrLoadModule("/src/modules/writeback/hooks/useWritebackList.ts"));
  ({ WritebackSearch: Search } = await server.ssrLoadModule(
    "/src/modules/writeback/components/WritebackSearch.tsx",
  ));
  ({ ParentOrderNumbers: ParentNumbers } = await server.ssrLoadModule(
    "/src/modules/writeback/components/ParentOrderNumbers.tsx",
  ));
});
after(async () => {
  await server?.close();
});
const render = (component, props) =>
  renderToStaticMarkup(createElement(MemoryRouter, null, createElement(component, props)));

test("回写概况展示后端计数并保持当前分组，徽标区分完成与阻塞", () => {
  const html = render(Stats, {
    counts: { all: 37, pending: 20, executing: 2, applied: 10, attention: 4, stale: 1 },
    selected: "attention",
    onSelect() {},
  });
  assert.equal((html.match(/aria-pressed="true"/g) || []).length, 1);
  for (const value of ["20 张", "2 张", "10 张", "4 张", "需处理", "回写中"]) assert.ok(html.includes(value));
  assert.match(html, /包含本次回写、同号已有登记及人工核实/);
  assert.doesNotMatch(html, /同号冲突/);
  assert.match(
    render(StateBadge, { task: { state: "applied", stateLabel: "NS 已登记" } }),
    /data-tone="success"/,
  );
  assert.match(
    render(StateBadge, { task: { state: "conflict", stateLabel: "NS 已有同号登记" } }),
    /data-tone="success"/,
  );
  assert.match(
    render(StateBadge, { task: { state: "blocked", stateLabel: "待处理" } }),
    /data-tone="danger"/,
  );
});

test("回写筛选从网址恢复关键词、分组与分页，非法分页使用默认值", () => {
  assert.deepEqual(
    readTaskQuery(
      new URLSearchParams(
        "keyword=旧词&taskNo=NSWB-1&invoiceNo=2601&supplierName=供应商&parentOrderNo=PO-100&group=attention&state=unknown&page=2&pageSize=50",
      ),
    ),
    {
      keyword: "旧词",
      taskNo: "NSWB-1",
      invoiceNo: "2601",
      supplierName: "供应商",
      parentOrderNo: "PO-100",
      group: "attention",
      state: "unknown",
      page: 2,
      pageSize: 50,
    },
  );
  assert.deepEqual(readTaskQuery(new URLSearchParams("group=other&page=-2&pageSize=999")), {
    keyword: "",
    taskNo: "",
    invoiceNo: "",
    supplierName: "",
    parentOrderNo: "",
    group: "",
    state: "",
    page: 1,
    pageSize: 20,
  });
});
test("回写查询拆成四个输入，母采购单多条完整展示且不使用模拟默认值", () => {
  const query = readTaskQuery(
    new URLSearchParams("taskNo=NSWB-1&invoiceNo=2601&supplierName=供应商&parentOrderNo=PO-100"),
  );
  const html = render(Search, { query, states: [], busy: false, onSearch() {}, onReset() {} });
  assert.equal((html.match(/type="search"/g) || []).length, 4);
  for (const value of ["NSWB-1", "2601", "供应商", "PO-100"]) assert.ok(html.includes(`value="${value}"`));
  assert.doesNotMatch(html, /输入任务号、发票号码或供应商/);
  const parents = render(ParentNumbers, {
    task: {
      parentOrders: [
        { id: "100", number: "PO-100" },
        { id: "200", number: "PO-200" },
      ],
    },
  });
  assert.match(parents, /PO-100/);
  assert.match(parents, /PO-200/);
  assert.match(render(ParentNumbers, { task: { parentOrders: [] } }), /未记录/);
});
const allocation = {
  allocationId: "1",
  orderNo: "SUB-1",
  parentOrderNo: "PO-1",
  parentOrderId: "100",
  amount: "100.50",
};
const noActions = {
  refresh: false,
  confirm: false,
  confirmPreview: false,
  execute: false,
  resolve: false,
  markNotWritten: false,
};
const request = (changes = {}) => ({
  requestId: "0f8fad5b-d9cb-469f-a165-70867728950e",
  state: "pending",
  invoice: { number: "TEST-INVOICE", date: "2026-10-20", amount: "100.50" },
  preview: [
    {
      billId: "9",
      billNumber: "TEST-BILL",
      purchaseOrderId: "100",
      before: "30.00",
      amount: "100.50",
      after: "130.50",
      available: "970.00",
      detailsTotal: "20.00",
      difference: "10.00",
      consistent: false,
    },
  ],
  needsConfirmation: true,
  confirmedBy: null,
  confirmedAt: null,
  nsRecordId: null,
  sentAt: null,
  finishedAt: null,
  ...changes,
});
const handlers = {
  onRefresh() {},
  onConfirm() {},
  onConfirmPreview() {},
  onExecute() {},
  onResolve() {},
};
const task = (changes = {}) => ({
  id: "1",
  taskNo: "NSWB-test",
  invoiceId: "8",
  invoiceNo: "TEST-INVOICE",
  vendorName: "测试供应商",
  amount: "100.50",
  state: "needs_confirmation",
  stateLabel: "待确认账单",
  reason: "归属需要核实",
  revision: 3,
  historical: true,
  updatedAt: "2026-10-28",
  writeback: { allowed: false, reason: "NS 写入开关未开启" },
  allocations: [allocation],
  orders: [
    {
      subPurchaseOrderId: "200",
      orderNo: "SUB-1",
      parentOrderNo: "PO-1",
      parentOrderId: "100",
      amount: "100.50",
      lineCount: 1,
      eligibleBillIds: ["9"],
      allocations: [{ allocationId: "1", purchaseLineId: "10", amount: "100.50" }],
    },
  ],
  candidates: {
    queryId: "q1",
    readCompletedAt: "2026-10-28",
    purchaseOrders: [
      {
        id: "100",
        reason: "已查询",
        bills: [
          {
            billId: "9",
            billNumber: "TEST-BILL",
            purchaseOrderId: "100",
            subPurchaseOrderId: "",
            subsidiaryId: "1",
            currency: "CNY",
            availableInvoiceAmount: "1000.00",
            issues: ["缺少子采购关联"],
          },
        ],
      },
    ],
  },
  plan: null,
  request: null,
  actions: { ...noActions, refresh: true, confirm: true },
  querying: false,
  audit: [],
  ...changes,
});

test("调用真实准备接口并原样发送金额、版本和幂等编号", async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return new Response(JSON.stringify(task()), { status: 200 });
  };
  try {
    await api.listTasks({
      keyword: "",
      taskNo: "NSWB",
      invoiceNo: "2601",
      supplierName: "供应商",
      parentOrderNo: "PO-100",
      state: "ready",
      group: "pending",
      page: 2,
      pageSize: 20,
    });
    await api.refreshTask("1", 3);
    const body = {
      revision: 3,
      requestId: "request-fixed",
      confirmScope: true,
      evidence: "核实依据",
      orders: [{ subPurchaseOrderId: "200", billId: "9" }],
    };
    await api.confirmPlan("1", body);
    assert.match(calls[0].url, /\/api\/writeback\/tasks\?/);
    assert.match(calls[0].url, /page=2/);
    assert.match(calls[0].url, /group=pending/);
    const sent = new URL(calls[0].url, "http://localhost").searchParams;
    assert.equal(sent.get("supplierName"), "供应商");
    assert.equal(sent.get("parentOrderNo"), "PO-100");
    assert.equal(sent.get("invoiceNo"), "2601");
    assert.equal(sent.get("taskNo"), "NSWB");
    assert.equal(calls[1].url, "/api/writeback/tasks/1/refresh");
    assert.deepEqual(JSON.parse(calls[1].options.body), { revision: 3 });
    assert.deepEqual(JSON.parse(calls[2].options.body), body);
    assert.equal(
      calls.some((call) => /execute|preview|apply/.test(call.url)),
      false,
    );
    await api.confirmPreview("1", 4);
    await api.executeWrite("1", 5);
    const resolve = { revision: 6, outcome: "applied", evidence: "已在 NS 核实", nsRecordId: "7001" };
    await api.resolveWrite("1", resolve);
    assert.equal(calls[3].url, "/api/writeback/tasks/1/preview/confirm");
    assert.deepEqual(JSON.parse(calls[3].options.body), { revision: 4, confirmScope: true });
    assert.equal(calls[4].url, "/api/writeback/tasks/1/execute");
    assert.deepEqual(JSON.parse(calls[4].options.body), { revision: 5 });
    assert.equal(calls[5].url, "/api/writeback/tasks/1/resolve");
    assert.deepEqual(JSON.parse(calls[5].options.body), resolve);
  } finally {
    globalThis.fetch = original;
  }
});

test("保留后端版本冲突错误，不伪装成功", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ error: "候选版本已变化" }), { status: 409 });
  try {
    await assert.rejects(() => api.refreshTask("1", 2), /候选版本已变化/);
  } finally {
    globalThis.fetch = original;
  }
});

test("候选、历史风险与不写入状态明确展示", () => {
  const html = render(Content, { task: task(), busy: false, ...handlers });
  assert.match(html, /历史发票，须人工核实/);
  assert.match(html, /归属需要核实/);
  assert.match(html, /未明确关联/);
  assert.match(html, /确认并冻结方案/);
  assert.doesNotMatch(html, /确认执行|模拟成功|执行回写/);
});

test("查询发现同号登记时展示已有记录并隐藏确认与写入入口", () => {
  const current = task();
  const html = render(Content, {
    task: task({
      state: "conflict",
      stateLabel: "NS 已有同号登记",
      reason: "已拦截重复回写",
      actions: { ...noActions, refresh: true },
      candidates: {
        ...current.candidates,
        registrationCheck: {
          invoiceNumber: current.invoiceNo,
          records: [{ id: "7001", number: current.invoiceNo, date: "2026-10-30" }],
        },
      },
    }),
    busy: false,
    ...handlers,
  });
  assert.match(html, /NS 已有同号发票登记/);
  assert.match(html, /已拦截重复回写/);
  assert.match(html, /7001/);
  assert.match(html, /TEST-INVOICE/);
  assert.match(html, /2026-10-30/);
  assert.doesNotMatch(html, /确认并冻结方案|回写到 NS/);
});

test("失效任务保留历史方案，隐藏确认入口", () => {
  const html = render(Content, {
    task: task({
      state: "stale",
      stateLabel: "审核已失效",
      actions: noActions,
      plan: {
        allocations: [{ allocationId: "1", billId: "9", amount: "100.50" }],
        orders: [{ subPurchaseOrderId: "200", orderNo: "SUB-1", billId: "9", amount: "100.50" }],
        evidence: "原归属凭据",
        confirmedBy: "财务",
        confirmedAt: "2026-10-28",
      },
    }),
    busy: false,
    ...handlers,
  });
  assert.match(html, /历史冻结方案（当前不可用）/);
  assert.match(html, /原归属凭据/);
  assert.doesNotMatch(html, /确认并冻结方案/);
});

test("未查询和空结果独立展示", () => {
  for (const [candidates, expected] of [
    [null, /尚未查询账单/],
    [
      { readCompletedAt: "today", purchaseOrders: [{ id: "100", reason: "无账单", bills: [] }] },
      /未取得可用账单/,
    ],
  ]) {
    assert.match(
      render(Content, {
        task: task({ candidates, actions: { ...noActions, refresh: true } }),
        busy: false,
        ...handlers,
      }),
      expected,
    );
  }
});

test("确认表单保留十进制文本，提交中禁用编辑", () => {
  const html = render(Form, { task: task(), busy: true, onConfirm() {} });
  assert.match(html, /fieldset disabled/);
  assert.match(html, /value="100.50"/);
  assert.match(html, /采购子公司/);
  assert.doesNotMatch(html, /新增分配行|移除/);
  assert.match(html, /readOnly/);
});

test("累计与明细不一致时展示预览差额，确认前没有回写按钮", () => {
  const html = render(Content, {
    task: task({
      state: "needs_preview",
      stateLabel: "待确认回写预览",
      request: request(),
      actions: { ...noActions, confirmPreview: true },
    }),
    busy: false,
    ...handlers,
  });
  assert.match(html, /NS 回写预览/);
  assert.match(html, /130.50/);
  assert.match(html, /不一致，差额 10.00 元/);
  assert.match(html, /确认回写预览/);
  assert.doesNotMatch(html, /回写到 NS/);
});

test("后端允许写入时才显示回写按钮；不允许时展示原因", () => {
  const ready = (allowed) =>
    render(Content, {
      task: task({
        state: "ready",
        stateLabel: "待写入 NS",
        writeback: { allowed, reason: allowed ? "可写入 NS" : "该供应商尚未列入回写白名单" },
        request: request({
          needsConfirmation: false,
          preview: [{ ...request().preview[0], consistent: true }],
        }),
        actions: { ...noActions, execute: allowed },
      }),
      busy: false,
      ...handlers,
    });
  assert.match(ready(true), /回写到 NS/);
  assert.doesNotMatch(ready(false), /回写到 NS/);
  assert.match(ready(false), /暂不能写入：该供应商尚未列入回写白名单/);
});

test("提交即显示正在回写，后端执行中即使保留旧允许动作也不能重复点击", () => {
  for (const [state, writing] of [
    ["ready", true],
    ["executing", false],
  ]) {
    const html = render(Content, {
      task: task({
        state,
        request: request({ state: state === "executing" ? "executing" : "pending" }),
        actions: { ...noActions, execute: true },
      }),
      busy: writing,
      writing,
      ...handlers,
    });
    assert.match(html, /disabled="" aria-busy="true"[^>]*>正在回写…/);
    assert.doesNotMatch(html, />回写到 NS</);
    if (writing) assert.match(html, /正在回写 NS/);
  }
});

test("部分完成只能标记已登记；结果不明可标记未写入，均无直接重发", () => {
  const view = (state, markNotWritten) =>
    render(Content, {
      task: task({
        state,
        stateLabel: state === "partial" ? "部分写入，待核实" : "结果不明，待核实",
        request: request({ state, nsRecordId: state === "partial" ? "7001" : null }),
        actions: { ...noActions, resolve: true, markNotWritten },
      }),
      busy: false,
      ...handlers,
    });
  const partial = view("partial", false);
  assert.match(partial, /核实 NS 写入结果/);
  assert.match(partial, /NS 供应商发票记录 ID：7001/);
  assert.doesNotMatch(partial, /NS 没有任何写入/);
  const unknown = view("unknown", true);
  assert.match(unknown, /NS 没有任何写入，可重新写入/);
  assert.doesNotMatch(unknown, /重试|回写到 NS/);
});

test("同一子采购单三条明细只需选择一次目标账单，后端金额原样展示", () => {
  const value = task();
  value.orders[0] = {
    ...value.orders[0],
    amount: "1011.00",
    lineCount: 3,
    allocations: [1, 2, 3].map((id) => ({
      allocationId: String(id),
      purchaseLineId: String(id),
      amount: "337.00",
    })),
  };
  const html = render(Form, { task: value, busy: false, onConfirm() {} });
  assert.equal((html.match(/<select/g) || []).length, 1);
  assert.match(html, /value="1011.00"/);
  assert.doesNotMatch(html, /337.00|新增分配行|移除/);
  assert.match(render(Content, { task: value, busy: false, ...handlers }), /3 条明细/);
});
