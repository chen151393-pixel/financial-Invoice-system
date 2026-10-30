import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
import { linkedMatching } from "./fixtures/linked-matching.mjs";

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

test("已关联整单默认展示详细比对和审核依据，不再显示无待审建议", async () => {
  const { InvoiceLinePanel } = await server.ssrLoadModule(
    "/src/modules/matching/components/InvoiceLinePanel.tsx",
  );
  const value = linkedMatching();
  const html = renderToStaticMarkup(
    createElement(InvoiceLinePanel, {
      ...value,
      invoiceId: "1",
      invoiceVersionId: "3",
      replacements: [],
      busy: false,
      actions: { cancel: async () => true, search: async () => ({ rows: [] }) },
    }),
  );
  for (const label of [
    "已关联整单",
    "整张子采购单合计",
    "合计金额",
    "税额",
    "查看子采购明细",
    "已核对票面和整单",
    "测试审核员",
    "删除关联",
  ])
    assert.ok(html.includes(label), label);
  assert.doesNotMatch(html, /本行没有待审核建议|确认整单通过|驳回整单|确认通过|取消分配/);
  assert.equal((html.match(/aria-label="整单比对 SUB-TEST-1"/g) || []).length, 1);
});

test("人工整单关联不显示虚构的零置信度", async () => {
  const { GroupComparisonCard } = await server.ssrLoadModule(
    "/src/modules/matching/components/GroupComparisonCard.tsx",
  );
  const value = linkedMatching();
  const group = value.linkedGroups[0];
  group.confidence = null;
  group.tier = "manual";
  group.items[0].confidence = null;
  group.items[0].tier = "manual";
  const html = renderToStaticMarkup(
    createElement(GroupComparisonCard, { group, item: value.item, invoice: value.invoice, readOnly: true }),
  );
  assert.match(html, /人工关联/);
  assert.doesNotMatch(html, /0%|匹配置信度|确认整单通过|驳回整单/);
});

test("旧后端或逐行关联也能查看详细比对，多条已关联全部保留", async () => {
  const { InvoiceLinePanel } = await server.ssrLoadModule(
    "/src/modules/matching/components/InvoiceLinePanel.tsx",
  );
  const value = linkedMatching();
  delete value.linkedGroups;
  value.item.allocations.push({
    ...value.item.allocations[0],
    id: "2",
    purchase: { ...value.item.allocations[0].purchase, orderNo: "SUB-TEST-2" },
  });
  const html = renderToStaticMarkup(
    createElement(InvoiceLinePanel, {
      ...value,
      invoiceId: "1",
      invoiceVersionId: "3",
      replacements: [],
      busy: false,
      actions: { cancel: async () => true, search: async () => ({ rows: [] }) },
    }),
  );
  assert.match(html, /比对记录 1/);
  assert.match(html, /比对记录 2/);
  assert.match(html, /发票行与子采购行逐项比对/);
  assert.doesNotMatch(html, /本行没有待审核建议|确认通过|取消分配/);
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

test("手动关联按整张子采购单查询并整单提交；明细只读，不提交逐条数量", async () => {
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
    note: "发票少开，其余按差异结束",
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
        parentOrderNo: "YE-CY20260410-F114",
        supplier: "东莞市创远智能设备有限公司",
        company: "上海毅鑫实业有限公司",
        recordNumbers: ["CD000901"],
        unit: "台",
        currency: "CNY",
        remainingQuantity: "288",
        remainingAmount: "22602.24",
        confidence: "62",
        tier: "medium",
        checks: [],
        block: "",
        lines: [line("31", "迷你烫画机", "192", "15068.16"), line("32", "迷你烫画机", "96", "7534.08")],
      },
      origin: "best",
      item: { id: "5", lineNo: "1", item: "*机械设备*烫画机", quantity: "72", unit: "台", amount: "5101.20" },
      invoice: { number: "26442000012361004566", seller: "东莞市创远智能设备有限公司", currency: "CNY" },
      invoiceId: "28",
      invoiceVersionId: "7",
      replaceId: "",
      reason: "",
      busy: false,
      onCreate: async () => true,
    }),
  );
  assert.match(html, /共 2 行明细/);
  // 默认候选与自动建议同样展示整单比对：来源标记、置信度、发票行与整单合计两侧摘要
  assert.match(html, /置信度最高 · 未保存/);
  assert.match(html, /中置信度/);
  assert.match(html, /进项发票行/);
  assert.match(html, /整单应开 288 台 · 含税合计 22602.24 CNY/);
  assert.match(html, /母采购单 YE-CY20260410-F114/);
  assert.match(html, />192</);
  assert.match(html, /7534.08 CNY/);
  assert.doesNotMatch(html, /本票分配数量|<input/);
  assert.match(html, /按差异结束/);
  assert.match(html, /保存整单关联并通过/);
});

test("手动关联：无建议时打开即查询默认候选，其余情况收起且不自动查询", async () => {
  const { ManualAllocation } = await server.ssrLoadModule(
    "/src/modules/matching/components/ManualAllocation.tsx",
  );
  const props = {
    invoiceId: "28",
    invoiceVersionId: "7",
    item: { id: "5", lineNo: "1" },
    invoice: { number: "1", currency: "CNY" },
    busy: false,
    search: async () => ({ rows: [], total: 0 }),
    replacements: [],
    onCreate: async () => true,
  };
  const auto = renderToStaticMarkup(createElement(ManualAllocation, { ...props, autoLoad: true }));
  assert.match(auto, /第 1 行 · 关联整张子采购单/);
  assert.match(auto, /没有待审核建议/);
  assert.match(auto, /按单号改选/);
  assert.match(auto, /至少 3 个字符/);
  assert.match(auto, /正在查询候选子采购单/);
  const folded = renderToStaticMarkup(createElement(ManualAllocation, { ...props, autoLoad: false }));
  assert.match(folded, /aria-expanded="false"[^>]*>手动关联</);
  assert.doesNotMatch(folded, /正在查询候选子采购单|按单号改选|查询子采购单/);
});
