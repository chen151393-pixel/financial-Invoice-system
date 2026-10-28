import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import vm from "node:vm";

const code = await readFile(new URL("../vendor_bill_query_restlet.js", import.meta.url), "utf8");

// 伪造 N/search：按检索类型返回预置行，行值按列标签读取，并记录全部检索条件。
function service(data = {}, options = {}) {
  let api;
  const calls = [];
  const ranges = [];
  const logs = [];
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
      if (input.columns.some((column) => column.name === "voided")) {
        throw new Error("SSS_INVALID_SRCH_COL: voided");
      }
      if (options.failType === input.type) throw new Error("private NS error");
      // 只模拟本脚本用到的 anyof 条件与作废筛选，其余条件由断言检查。
      const matchers = {
        internalid: (row) => row.id,
        createdfrom: (row) => row.values.purchaseOrderId,
        custrecord_swc_vid_bill: (row) => row.values.billId,
        voided: (row) => row.values.voided,
      };
      const matches = (filter, row) =>
        filter[1] === "is"
          ? matchers[filter[0]](row) === filter[2]
          : [filter[2]].flat().includes(matchers[filter[0]](row));
      const rows = (fixtures[input.type] ?? []).filter((row) =>
        input.filters.every(
          (filter) => !Array.isArray(filter) || !matchers[filter[0]] || matches(filter, row),
        ),
      );
      return {
        run: () => ({
          getRange: ({ start, end }) => {
            ranges.push({
              type: input.type,
              start,
              end,
              voided: input.filters.some((filter) => Array.isArray(filter) && filter[0] === "voided"),
            });
            if (end - start > 1000) throw new Error("SSS_SEARCH_RESULT_LIMIT_EXCEEDED");
            return rows.slice(start, end).map((row) => ({
              id: row.id,
              getValue: (column) => row.values[column.label] ?? "",
              getText: (column) => row.texts?.[column.label] ?? "",
            }));
          },
        }),
      };
    },
  };
  vm.runInNewContext(code, {
    define: (_deps, factory) => {
      api = factory(
        search,
        {
          accountId: "5939865",
          getCurrentScript: () => ({ getRemainingUsage: () => options.usage ?? 1000 }),
        },
        {
          audit: (entry) => logs.push({ level: "audit", ...entry }),
          error: (entry) => logs.push({ level: "error", ...entry }),
        },
      );
    },
  });
  // RESTlet 结果按 JSON 返回给后端；序列化后比较，也避开 vm 跨上下文的原型差异。
  return { api: { post: (input) => JSON.parse(JSON.stringify(api.post(input))) }, calls, logs, ranges };
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

// 明细逐行返回，脚本内按账单合计。
function details(billId, ...amounts) {
  return amounts.map((amount, index) => ({ id: `${billId}${index}`, values: { billId, amount } }));
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
    customrecord_swc_vendor_invoice_detail: details("9001", "1000.40", "100.1"),
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
  // 明细不做 GROUP 汇总（NS 不允许按该字段分组），作废状态只作为筛选条件。
  const detailSearch = calls.find((call) => call.type === "customrecord_swc_vendor_invoice_detail");
  assert.ok(detailSearch.columns.every((item) => !item.summary));
  const billColumns = calls.filter((call) => call.type === "vendorbill").flatMap((call) => call.columns);
  assert.ok(billColumns.every((item) => item.name !== "voided"));
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
    customrecord_swc_vendor_invoice_detail: details("9002", "480"),
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

test("已作废账单单独筛出并照常返回", () => {
  const { api, calls } = service({
    vendorbill: [bill("9020", "501", { voided: "T" }), bill("9021", "501")],
  });
  const bills = api.post(request()).purchaseOrders[0].bills;
  assert.deepEqual(
    bills.map((item) => [item.billId, item.voided]),
    [
      ["9020", true],
      ["9021", false],
    ],
  );
  const voidSearch = calls.filter((call) => call.type === "vendorbill")[1];
  assert.deepEqual([...voidSearch.filters.at(-1)], ["voided", "is", "T"]);
});

test("明细超过逐行上限时返回超限，不截断合计", () => {
  const many = details("9001", ...Array.from({ length: 5001 }, () => "1"));
  const result = service({
    vendorbill: [bill("9001", "501")],
    customrecord_swc_vendor_invoice_detail: many,
  }).api.post(request());
  assert.equal(result.error.code, "QUERY_LIMIT");
});

test("执行日志记录阶段与修订号，接口只返回固定错误码", () => {
  const failed = service(
    { vendorbill: [bill("9001", "501")] },
    { failType: "customrecord_swc_vendor_invoice_detail" },
  );
  assert.deepEqual(failed.api.post(request()).error, { code: "QUERY_FAILED" });
  const entry = JSON.parse(failed.logs.at(-1).details);
  assert.equal(entry.stage, "invoice_detail_lookup");
  assert.match(entry.revision, /^\d{4}-\d{2}-\d{2}\.\d+$/);
  const ok = service();
  assert.equal(ok.api.post(request()).complete, true);
  assert.equal(JSON.parse(ok.logs.at(-1).details).stage, "complete");
});

test("1000 行正常读取，1001 行分次探测后明确拒绝，单次不超过 NS 上限", () => {
  for (const count of [999, 1000, 1001]) {
    const { api, ranges } = service({
      vendorbill: Array.from({ length: count }, () => bill("9001", "501")),
    });
    const result = api.post(request());
    assert.equal(result.complete, count <= 1000);
    if (count > 1000) assert.equal(result.error.code, "QUERY_LIMIT");
    const billRanges = ranges.filter((range) => range.type === "vendorbill" && !range.voided);
    assert.deepEqual(
      billRanges.map(({ start, end }) => [start, end]),
      count < 1000
        ? [[0, 1000]]
        : [
            [0, 1000],
            [1000, 1001],
          ],
    );
    assert.ok(ranges.every(({ start, end }) => end - start <= 1000));
  }
});

test("分阶段错误仅写 NS 后台日志，接口不泄露原始异常", () => {
  for (const [type, stage] of [
    ["vendor", "vendor_lookup"],
    ["purchaseorder", "purchase_order_lookup"],
    ["vendorbill", "bill_lookup"],
    ["customrecord_swc_vendor_invoice_detail", "invoice_detail_lookup"],
  ]) {
    const { api, logs } = service({ vendorbill: [bill("9001", "501")] }, { failType: type });
    const result = api.post(request());
    assert.deepEqual(result.error, { code: "QUERY_FAILED" });
    assert.equal(logs.length, 1);
    assert.equal(logs[0].level, "error");
    assert.equal(logs[0].title, "VENDOR_BILL_QUERY_FAILED");
    const logged = JSON.parse(logs[0].details);
    assert.equal(logged.stage, stage);
    assert.equal(logged.vendorId, "88");
    assert.equal(logged.message, "private NS error");
    assert.ok(!JSON.stringify(result).includes("private NS error"));
  }
  const { api, logs } = service();
  api.post({ secret: "never-log-this" });
  assert.ok(!JSON.stringify(logs).includes("never-log-this"));
  assert.equal(JSON.parse(logs[0].details).stage, "request_validation");
  api.post(request());
  assert.equal(logs[1].level, "audit");
  assert.equal(JSON.parse(logs[1].details).stage, "complete");
});

test("帝奇母单样本：已付款但未收票，付款仍计入应收票额度", () => {
  const { api, logs } = service({
    vendor: [{ id: "8879", values: { code: "8879", name: "中山帝奇新材料有限公司" } }],
    purchaseorder: [
      {
        ...order("308488", "8879"),
        values: { ...order("308488", "8879").values, number: "YE-DQ20260624-Z010" },
      },
    ],
    vendorbill: [
      bill("395762", "308488", {
        vendorId: "8879",
        billNumber: "VENDBILL35675",
        remaining: "0",
        received: "0",
        applyingType: "VendPymt",
        applied: "11184.68",
      }),
    ],
  });
  const result = api.post({ action: "bills", vendorId: "8879", purchaseOrderIds: ["308488"] });
  assert.equal(result.complete, true);
  assert.equal(result.purchaseOrders[0].number, "YE-DQ20260624-Z010");
  const found = result.purchaseOrders[0].bills[0];
  assert.equal(found.billNumber, "VENDBILL35675");
  assert.equal(found.amounts.payable, "11184.68");
  assert.equal(found.amounts.available, "11184.68");
  assert.deepEqual(found.details, { count: 0, total: "0.00" });
  assert.equal(JSON.parse(logs[0].details).billCount, 1);
  assert.equal(JSON.parse(logs[0].details).revision, "2026-10-28.3");
});
