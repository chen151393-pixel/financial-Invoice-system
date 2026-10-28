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
  writeback: { allowed: false, reason: "NS 写入尚未接入" },
  allocations: [allocation],
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
  actions: { refresh: true, confirm: true },
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
      allocations: [{ allocationId: "1", billId: "9", amount: "100.50" }],
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
  const html = render(Content, { task: task(), busy: false, onRefresh() {}, onConfirm() {} });
  assert.match(html, /历史发票，须人工核实/);
  assert.match(html, /NS 写入尚未接入/);
  assert.match(html, /未明确关联/);
  assert.match(html, /确认并冻结方案/);
  assert.doesNotMatch(html, /确认执行|模拟成功|执行回写/);
});

test("失效任务保留历史方案，隐藏确认入口", () => {
  const html = render(Content, {
    task: task({
      state: "stale",
      stateLabel: "审核已失效",
      actions: { refresh: false, confirm: false },
      plan: {
        allocations: [{ allocationId: "1", billId: "9", amount: "100.50" }],
        evidence: "原归属凭据",
        confirmedBy: "财务",
        confirmedAt: "2026-10-28",
      },
    }),
    busy: false,
    onRefresh() {},
    onConfirm() {},
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
        task: task({ candidates, actions: { refresh: true, confirm: false } }),
        busy: false,
        onRefresh() {},
        onConfirm() {},
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
  assert.match(html, /新增分配行/);
});
