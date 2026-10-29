import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

let server, api;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  api = await server.ssrLoadModule("/src/modules/matching/api/index.ts");
});
after(async () => {
  await server?.close();
});

test("整单候选传递查询参数，确认绑定预览摘要及同一请求号；页面不再提交换算字段", async () => {
  const original = globalThis.fetch,
    calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return new Response(JSON.stringify({ rows: [], total: 0, page: 1, pages: 1 }));
  };
  try {
    const query = {
      invoiceId: "28",
      keyword: "YE-DQ20260624-Z010",
      page: 2,
    };
    await api.findOrderCandidates(query);
    const body = {
      requestId: "same-request",
      invoiceId: "28",
      invoiceVersionId: "7",
      purchaseOrderId: "248",
      fingerprint: "a".repeat(64),
      note: "已核实整单",
    };
    await api.confirmOrder(body);
    assert.equal(calls[0].url, "/api/matching/order-candidates/query");
    assert.deepEqual(calls[0].body, query);
    assert.equal(calls[1].url, "/api/matching/orders/confirm");
    assert.deepEqual(calls[1].body, body);
    assert.equal(calls.length, 2);
  } finally {
    globalThis.fetch = original;
  }
});

test("整单确认冲突保留后端原因，且不自动重试写操作", async () => {
  const original = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return new Response(JSON.stringify({ error: "采购来源已变化，请刷新整单预览" }), { status: 409 });
  };
  try {
    await assert.rejects(() => api.confirmOrder({}), /采购来源已变化/);
    assert.equal(calls, 1);
  } finally {
    globalThis.fetch = original;
  }
});

test("整单建议整组通过与驳回：只提交发票、版本与选填说明", async () => {
  const original = globalThis.fetch,
    calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return new Response(JSON.stringify({ items: [], groups: [] }));
  };
  try {
    const group = "8f0c9a52-6f2e-4a51-9c33-0d1f2a3b4c5d";
    await api.confirmGroup(group, "28", "7", "");
    await api.rejectGroup(group, "28", "金额待核");
    assert.deepEqual(calls, [
      {
        url: `/api/matching/groups/${group}/confirm`,
        body: { invoiceId: "28", invoiceVersionId: "7", note: "" },
      },
      { url: `/api/matching/groups/${group}/reject`, body: { invoiceId: "28", note: "金额待核" } },
    ]);
  } finally {
    globalThis.fetch = original;
  }
});

test("手动关联按整张子采购单查询并提交全部明细；选中后明细默认取后端剩余应开", async () => {
  const original = globalThis.fetch,
    calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return new Response(JSON.stringify({ rows: [], total: 0, items: [], groups: [] }));
  };
  const body = {
    requestId: "same-request",
    invoiceId: "28",
    invoiceItemId: "5",
    purchaseOrderId: "248",
    invoiceVersionId: "7",
    lines: [
      { purchaseLineId: "31", quantity: "72", amount: "5101.20" },
      { purchaseLineId: "32", quantity: "0", amount: "0" },
    ],
    note: "部分开票",
    replaceAllocationId: null,
    replaceReason: "",
  };
  try {
    await api.findManualOrders("28", "5", "YE-CY20260410-F114-1");
    await api.createManualOrder(body);
    assert.deepEqual(calls, [
      {
        url: "/api/matching/manual-orders/candidates/query",
        body: { invoiceId: "28", invoiceItemId: "5", keyword: "YE-CY20260410-F114-1" },
      },
      { url: "/api/matching/manual-orders", body },
    ]);
  } finally {
    globalThis.fetch = original;
  }
  const { OrderShareForm } = await server.ssrLoadModule(
    "/src/modules/matching/components/OrderShareForm.tsx",
  );
  const line = (id, item, quantity, amount) => ({
    purchaseLineId: id,
    item,
    specification: "",
    unit: "台",
    currency: "CNY",
    remainingQuantity: quantity,
    remainingAmount: amount,
  });
  const html = renderToStaticMarkup(
    createElement(OrderShareForm, {
      order: {
        purchaseOrderId: "248",
        orderNo: "YE-CY20260410-F114-1",
        supplier: "东莞市创远智能设备有限公司",
        checks: [],
        block: "",
        lines: [line("31", "迷你烫画机", "192", "15068.16"), line("32", "迷你烫画机", "96", "7534.08")],
      },
      item: { id: "5" },
      invoiceId: "28",
      invoiceVersionId: "7",
      replaceId: "",
      reason: "",
      busy: false,
      onCreate: async () => true,
    }),
  );
  assert.match(html, /共 2 行明细/);
  assert.match(html, /value="192"/);
  assert.match(html, /value="7534.08"/);
  assert.match(html, /aria-label="迷你烫画机 本票分配数量"/);
  assert.match(html, /保存整单关联并通过/);
});
