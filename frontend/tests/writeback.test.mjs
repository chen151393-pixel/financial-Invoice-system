import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { createServer } from "vite";

let server, api, Content, Form;
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
});
after(async () => {
  await server?.close();
});
const render = (component, props) =>
  renderToStaticMarkup(createElement(MemoryRouter, null, createElement(component, props)));
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
    await api.listTasks({ keyword: "供应商", state: "ready", page: 2, pageSize: 20 });
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
