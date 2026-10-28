import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import vm from "node:vm";

const code = await readFile(new URL("../vendor_bill_query_restlet.js", import.meta.url), "utf8");

// 伪造 N/search：按检索类型返回预置行，行值按列标签读取，并记录全部检索条件。
function service(data = {}, options = {}) {
  let api;
  const calls = [];
  const fixtures = {
    vendor: [{ id: "88", values: { code: "V088", name: "测试供应商" } }],
    purchaseorder: [order("501"), order("502")],
    vendorbill: [],
    customrecord_swc_vendor_invoice_detail: [],
    ...data,
  };
  const search = {
    Summary: { GROUP: "GROUP", SUM: "SUM", COUNT: "COUNT" },
    createColumn: (input) => ({ ...input }),
    create(input) {
      calls.push(input);
      if (options.failType === input.type) throw new Error("private NS error");
      // 只模拟本脚本用到的 anyof 条件，其余条件由断言检查。
      const matchers = {
        internalid: (row) => row.id,
        createdfrom: (row) => row.values.purchaseOrderId,
        custrecord_swc_vid_bill: (row) => row.values.billId,
      };
      const rows = (fixtures[input.type] ?? []).filter((row) =>
        input.filters.every(
          (filter) =>
            !Array.isArray(filter) ||
            filter[1] !== "anyof" ||
            !matchers[filter[0]] ||
            [filter[2]].flat().includes(matchers[filter[0]](row)),
        ),
      );
      return {
        run: () => ({
          getRange: ({ start, end }) =>
            rows.slice(start, end).map((row) => ({
              id: row.id,
              getValue: (column) => row.values[column.label] ?? "",
              getText: (column) => row.texts?.[column.label] ?? "",
            })),
        }),
      };
    },
  };
  vm.runInNewContext(code, {
    define: (_deps, factory) => {
      api = factory(search, {
        accountId: "5939865",
        getCurrentScript: () => ({ getRemainingUsage: () => options.usage ?? 1000 }),
      });
    },
  });
  // RESTlet 结果按 JSON 返回给后端；序列化后比较，也避开 vm 跨上下文的原型差异。
  return { api: { post: (input) => JSON.parse(JSON.stringify(api.post(input))) }, calls };
}

function order(id, vendorId = "88") {
  return {
    id,
    values: { number: `PO${id}`, vendorId, subsidiaryId: "3", currencyId: "1" },
    texts: { currencyId: "人民币" },
  };
}

function bill(id, purchaseOrderId, values = {}) {
  return {
    id,
    values: {
      billNumber: `BILL${id}`,
      vendorId: "88",
      purchaseOrderId,
      subPurchaseOrderId: "",
      subsidiaryId: "3",
      currencyId: "1",
      approvalStatus: "2",
      voided: "F",
      taxTotal: "-130",
      remaining: "1000",
      received: "0",
      applyingType: "",
      applied: "0",
      ...values,
    },
    texts: { currencyId: "人民币" },
  };
}

function detail(billId, total, count = "1") {
  return { id: undefined, values: { billId, total, count } };
}

const request = (purchaseOrderIds = ["501"]) => ({ action: "bills", vendorId: "88", purchaseOrderIds });

test("按母单返回全部账单，额度按平台口径用整数分计算", () => {
  const { api, calls } = service({
    vendorbill: [
      bill("9001", "501", {
        remaining: "200",
        received: "1100.5",
        applyingType: "VendPymt",
        applied: "1000",
      }),
      bill("9001", "501", { remaining: "200", received: "1100.5", applyingType: "VendCred", applied: "50" }),
      bill("9001", "501", { remaining: "200", received: "1100.5", applyingType: "VendPymt", applied: ".1" }),
    ],
    customrecord_swc_vendor_invoice_detail: [detail("9001", "1100.50", "2")],
  });
  const result = api.post(request());
  assert.equal(result.complete, true);
  assert.equal(result.contractVersion, 3);
  assert.equal(result.status, "OK");
  const [po] = result.purchaseOrders;
  assert.equal(po.status, "FOUND");
  assert.equal(po.currencyName, "人民币");
  const [found] = po.bills;
  assert.deepEqual(found.amounts, {
    remaining: "200.00",
    applied: "1000.10",
    payable: "1200.10",
    received: "1100.50",
    available: "99.60",
  });
  assert.deepEqual(found.details, { count: 2, total: "1100.50" });
  assert.equal(found.consistent, true);
  assert.equal(found.hasTax, true);
  assert.equal(found.voided, false);
  // 查账单不按日期、税额或可收金额过滤，避免“查不到”含义混杂。
  const billSearch = calls.find((call) => call.type === "vendorbill");
  assert.ok(billSearch.filters.some((filter) => filter[0] === "createdfrom" && filter[2].includes("501")));
  assert.ok(!JSON.stringify(billSearch.filters).includes("trandate"));
  assert.ok(!JSON.stringify(billSearch.filters).includes("taxtotal"));
});

test("已登记满、税额为 0、未审批的账单照常返回，由后端判定", () => {
  const { api } = service({
    vendorbill: [
      bill("9002", "501", { remaining: "0", received: "500", applyingType: "VendPymt", applied: "500" }),
      bill("9003", "501", { taxTotal: "0", approvalStatus: "1" }),
    ],
    customrecord_swc_vendor_invoice_detail: [detail("9002", "480")],
  });
  const bills = api.post(request()).purchaseOrders[0].bills;
  assert.deepEqual(
    bills.map((item) => [item.billId, item.amounts.available, item.hasTax, item.approvalStatus]),
    [
      ["9002", "0.00", true, "2"],
      ["9003", "1000.00", false, "1"],
    ],
  );
  assert.equal(bills[0].consistent, false);
  assert.deepEqual(bills[1].details, { count: 0, total: "0.00" });
  assert.equal(bills[1].consistent, true);
});

test("多个母单按请求顺序返回，分别标出不存在、供应商不符与无账单", () => {
  const { api, calls } = service({
    purchaseorder: [order("501"), order("503", "77"), order("504")],
    vendorbill: [bill("9010", "501"), bill("9004", "501", { subPurchaseOrderId: "2405" })],
  });
  const result = api.post(request(["502", "501", "503", "504"]));
  assert.deepEqual(
    result.purchaseOrders.map((po) => [po.id, po.status, po.bills.map((item) => item.billId)]),
    [
      ["502", "PO_NOT_FOUND", []],
      ["501", "FOUND", ["9004", "9010"]],
      ["503", "VENDOR_MISMATCH", []],
      ["504", "NO_BILLS", []],
    ],
  );
  assert.equal(result.purchaseOrders[1].bills[0].subPurchaseOrderId, "2405");
  // 供应商不符的母单不参与账单检索。
  const billSearch = calls.find((call) => call.type === "vendorbill");
  assert.deepEqual([...billSearch.filters.at(-1)[2]], ["501", "504"]);
});

test("供应商不存在时不再检索采购单和账单", () => {
  const { api, calls } = service({ vendor: [] });
  const result = api.post(request());
  assert.equal(result.complete, true);
  assert.equal(result.status, "VENDOR_NOT_FOUND");
  assert.deepEqual(
    calls.map((call) => call.type),
    ["vendor"],
  );
});

test("无效和越界请求在检索前拒绝", () => {
  for (const input of [
    null,
    [],
    {},
    { action: "match", vendorId: "88", purchaseOrderIds: ["501"] },
    { action: "bills", vendorId: "88" },
    { action: "bills", vendorId: "88", purchaseOrderIds: [] },
    { action: "bills", vendorId: "88", purchaseOrderIds: ["501", "501"] },
    { action: "bills", vendorId: "88", purchaseOrderIds: ["PO501"] },
    { action: "bills", vendorId: "0", purchaseOrderIds: ["501"] },
    { action: "bills", vendorId: 88, purchaseOrderIds: ["501"] },
    {
      action: "bills",
      vendorId: "88",
      purchaseOrderIds: Array.from({ length: 21 }, (_, i) => String(i + 1)),
    },
    { action: "bills", vendorId: "88", purchaseOrderIds: ["501"], recordType: "vendorbill" },
  ]) {
    const { api, calls } = service();
    const result = api.post(input);
    assert.equal(result.complete, false);
    assert.equal(result.error.code, "INVALID_REQUEST");
    assert.equal(calls.length, 0);
  }
});

test("金额格式或检索结果异常时整单失败，不返回部分结果", () => {
  for (const values of [
    { remaining: "12.345" },
    { remaining: "1,000.00" },
    { received: "abc" },
    { approvalStatus: "9" },
    { voided: "maybe" },
    { vendorId: "" },
  ]) {
    const result = service({ vendorbill: [bill("9001", "501", values)] }).api.post(request());
    assert.equal(result.complete, false, JSON.stringify(values));
    assert.equal(result.error.code, "INVALID_RESULT");
    assert.equal(result.purchaseOrders, undefined);
  }
  // 同一账单展开行的主行字段不一致。
  const split = service({
    vendorbill: [bill("9001", "501"), bill("9001", "501", { received: "1" })],
  }).api.post(request());
  assert.equal(split.error.code, "INVALID_RESULT");
});

test("检索超限、额度不足或 NS 异常时返回固定错误码，不泄露原文", () => {
  const many = Array.from({ length: 1001 }, () => bill("9001", "501"));
  assert.equal(service({ vendorbill: many }).api.post(request()).error.code, "QUERY_LIMIT");
  assert.equal(service({}, { usage: 100 }).api.post(request()).error.code, "QUERY_LIMIT");
  const failed = service({}, { failType: "vendorbill" }).api.post(request());
  assert.deepEqual(failed.error, { code: "QUERY_FAILED" });
  assert.ok(!JSON.stringify(failed).includes("private"));
});
