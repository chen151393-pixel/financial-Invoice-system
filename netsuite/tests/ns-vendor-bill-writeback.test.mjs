import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import vm from "node:vm";

const code = await readFile(new URL("../vendor_bill_writeback_restlet.js", import.meta.url), "utf8");

// 伪造 N/search 与 N/record：账单按检索类型返回预置行，写入动作全部记录下来供断言。
function service(data = {}, options = {}) {
  let api;
  const searches = [];
  const ranges = [];
  const writes = { created: [], submitted: [] };
  const fixtures = {
    customrecord_swc_vendor_invoice: [],
    vendorbill: [bill("9001", "501")],
    ...data,
  };
  const stored = new Map();
  const search = {
    Type: { VENDOR_BILL: "vendorbill" },
    createColumn: (input) => ({ ...input }),
    create(input) {
      searches.push(input);
      if (options.failSearch === input.type) throw new Error("private NS error");
      const voidedOnly = input.filters.some((filter) => Array.isArray(filter) && filter[0] === "voided");
      const ids = input.filters.find((filter) => Array.isArray(filter) && filter[0] === "internalid")?.[2];
      const rows = (fixtures[input.type] ?? []).filter(
        (row) => (!ids || [ids].flat().includes(row.id)) && (!voidedOnly || row.values.voided === "T"),
      );
      return {
        run: () => ({
          getRange: ({ start, end }) => {
            ranges.push({ type: input.type, start, end });
            // 模拟 NS 单次范围限制；结果为空时也不能请求 1001 条。
            if (end - start > 1000) throw new Error("SSS_SEARCH_RESULT_LIMIT_EXCEEDED");
            return rows
              .slice(start, end)
              .map((row) => ({ id: row.id, getValue: (column) => row.values[column.label] ?? "" }));
          },
        }),
      };
    },
    lookupFields({ id, columns }) {
      const saved = stored.get(id) ?? {};
      const linked = options.dropLinks ? [] : (saved.custbody_swc_bill_vendor_num ?? []);
      return Object.fromEntries(
        columns.map((name) => [
          name,
          name === "custbody_swc_bill_vendor_num"
            ? linked.map((value) => ({ value: String(value), text: String(value) }))
            : String(saved[name] ?? ""),
        ]),
      );
    },
  };
  const record = {
    Type: { VENDOR_BILL: "vendorbill" },
    create({ type }) {
      const created = { type, values: {}, lines: [] };
      return {
        setValue: ({ fieldId, value }) => {
          created.values[fieldId] = value;
        },
        setSublistValue: ({ sublistId, fieldId, line, value }) => {
          created.lines[line] = { ...created.lines[line], sublistId, [fieldId]: value };
        },
        save: () => {
          if (options.failCreate) throw new Error("save failed");
          writes.created.push(created);
          return 7001;
        },
      };
    },
    submitFields(input) {
      if (options.failSubmit === input.id) throw new Error("submit failed");
      writes.submitted.push(input);
      stored.set(input.id, input.values);
    },
  };
  vm.runInNewContext(code, {
    define: (_deps, factory) => {
      api = factory(
        search,
        record,
        {
          accountId: "5939865",
          getCurrentScript: () => ({ getRemainingUsage: () => options.usage ?? 5000 }),
        },
        { audit: () => {}, error: () => {} },
      );
    },
  });
  return { api: { post: (input) => JSON.parse(JSON.stringify(api.post(input))) }, searches, writes, ranges };
}

function bill(id, purchaseOrderId, values = {}) {
  return {
    id,
    values: {
      billNumber: `BILL${id}`,
      vendorId: "88",
      purchaseOrderId,
      approvalStatus: "2",
      remaining: "1000",
      received: "100",
      invoices: "",
      applyingType: "",
      applied: "0",
      voided: "F",
      ...values,
    },
  };
}

const request = (changes = {}) => ({
  action: "apply",
  requestId: "0f8fad5b-d9cb-469f-a165-70867728950e",
  vendorId: "88",
  invoice: { number: "26332000002263007611", date: "2026-03-20", amount: "300.00" },
  bills: [{ billId: "9001", purchaseOrderId: "501", amount: "300.00", expectedBefore: "100.00" }],
  ...changes,
});

test("复核通过后一次建主记录与明细，账单累计按写前值加本次金额并回读核实", () => {
  const { api, writes } = service({
    vendorbill: [bill("9001", "501", { invoices: "11,12", applyingType: "VendPymt", applied: "200" })],
  });
  const result = api.post(request());
  assert.equal(result.complete, true);
  assert.equal(result.status, "APPLIED");
  assert.equal(result.written, true);
  assert.equal(result.invoiceRecordId, "7001");
  assert.deepEqual(result.bills, [
    {
      billId: "9001",
      billNumber: "BILL9001",
      status: "UPDATED",
      before: "100.00",
      amount: "300.00",
      after: "400.00",
      verified: true,
    },
  ]);
  const [created] = writes.created;
  assert.equal(created.type, "customrecord_swc_vendor_invoice");
  assert.equal(created.values.name, "26332000002263007611");
  assert.equal(created.values.custrecord_swc_vi_vendor, "88");
  // 日期按本地日期保存，避免时区差一天。
  const date = created.values.custrecord_swc_vi_billdate;
  assert.deepEqual([date.getFullYear(), date.getMonth(), date.getDate()], [2026, 2, 20]);
  assert.deepEqual(
    { ...created.lines[0] },
    {
      sublistId: "recmachcustrecord_swc_vid_main",
      custrecord_swc_vid_bill: "9001",
      custrecord_swc_vid_po: "501",
      custrecord_swc_vid_billamount: 1200,
      custrecord_swc_vid_billpaied: 100,
      custrecord_swc_cid_current_amount: 300,
    },
  );
  const [submitted] = writes.submitted;
  assert.equal(submitted.id, "9001");
  assert.equal(submitted.values.custbody_swc_vendor_amount, 400);
  assert.deepEqual([...submitted.values.custbody_swc_bill_vendor_num], ["11", "12", "7001"]);
});

test("同号发票已登记时返回冲突，不写入任何记录", () => {
  const { api, writes, searches } = service({
    customrecord_swc_vendor_invoice: [
      { id: "51601", values: { name: "26332000002263007611", date: "2026/3/20" } },
    ],
  });
  const result = api.post(request());
  assert.equal(result.status, "CONFLICT");
  assert.equal(result.written, false);
  assert.deepEqual(result.existing, [{ id: "51601", number: "26332000002263007611", date: "2026/3/20" }]);
  assert.equal(writes.created.length + writes.submitted.length, 0);
  const duplicate = searches.find((item) => item.type === "customrecord_swc_vendor_invoice");
  assert.ok(
    duplicate.filters.some((filter) => filter[0] === "custrecord_swc_vi_vendor" && filter[2] === "88"),
  );
  assert.ok(
    duplicate.filters.some(
      (filter) => filter[0] === "name" && filter[1] === "is" && filter[2] === request().invoice.number,
    ),
  );
  assert.ok(duplicate.filters.some((filter) => filter[0] === "isinactive" && filter[2] === "F"));
});

test("重复检查在 0、1、999、1000、1001 条边界均遵守单次 1000 条限制", () => {
  for (const count of [0, 1, 999, 1000, 1001]) {
    const existing = Array.from({ length: count }, (_, index) => ({
      id: String(50000 + index),
      values: { name: request().invoice.number, date: "2026/3/20" },
    }));
    const { api, writes, ranges } = service({ customrecord_swc_vendor_invoice: existing });
    const result = api.post(request());
    assert.ok(ranges.every(({ start, end }) => end - start <= 1000));
    if (count === 0) {
      assert.equal(result.status, "APPLIED");
    } else {
      assert.equal(writes.created.length + writes.submitted.length, 0);
      if (count <= 1000) {
        assert.equal(result.status, "CONFLICT");
        assert.equal(result.existing.length, count);
      } else {
        assert.equal(result.error.code, "QUERY_LIMIT");
        assert.equal(result.written, false);
      }
    }
    if (count >= 1000)
      assert.deepEqual(
        ranges
          .filter(({ type }) => type === "customrecord_swc_vendor_invoice")
          .map(({ start, end }) => [start, end]),
        [
          [0, 1000],
          [1000, 1001],
        ],
      );
  }
});

test("账单核销展开恰好 1000 行可完整校验；超过限制整单不写入", () => {
  for (const count of [1000, 1001]) {
    const { api, writes, ranges } = service({
      vendorbill: Array.from({ length: count }, () => bill("9001", "501")),
    });
    const result = api.post(request());
    assert.ok(ranges.every(({ start, end }) => end - start <= 1000));
    if (count === 1000) {
      assert.equal(result.status, "APPLIED");
      assert.equal(writes.submitted.length, 1);
    } else {
      assert.equal(result.error.code, "QUERY_LIMIT");
      assert.equal(result.written, false);
      assert.equal(writes.created.length + writes.submitted.length, 0);
    }
  }
});

test("账单归属、审批、作废、累计变化或超额时整单拒绝，不写入", () => {
  for (const [values, code, line] of [
    [{ vendorId: "77" }, "VENDOR_MISMATCH"],
    [{ purchaseOrderId: "502" }, "ORDER_MISMATCH"],
    [{ approvalStatus: "1" }, "NOT_APPROVED"],
    [{ voided: "T" }, "VOIDED"],
    [{ received: "150" }, "STALE"],
    [{ remaining: "350" }, "OVER_AVAILABLE"],
    [{}, "BILL_NOT_FOUND", { billId: "9999" }],
  ]) {
    const { api, writes } = service({ vendorbill: [bill("9001", "501", values)] });
    const input = request(
      line
        ? {
            bills: [
              { billId: line.billId, purchaseOrderId: "501", amount: "300.00", expectedBefore: "100.00" },
            ],
          }
        : {},
    );
    const result = api.post(input);
    assert.equal(result.status, "REJECTED", code);
    assert.equal(result.written, false);
    assert.ok(
      result.problems.some((item) => item.code === code),
      code,
    );
    assert.equal(writes.created.length + writes.submitted.length, 0, code);
  }
});

test("主记录建成后某张账单更新失败：返回部分完成，后续账单不再尝试", () => {
  const { api, writes } = service(
    { vendorbill: [bill("9001", "501"), bill("9002", "501"), bill("9003", "501")] },
    { failSubmit: "9002" },
  );
  const result = api.post(
    request({
      invoice: { number: "INV-1", date: "2026-03-20", amount: "300.00" },
      bills: [
        { billId: "9001", purchaseOrderId: "501", amount: "100.00", expectedBefore: "100.00" },
        { billId: "9002", purchaseOrderId: "501", amount: "100.00", expectedBefore: "100.00" },
        { billId: "9003", purchaseOrderId: "501", amount: "100.00", expectedBefore: "100.00" },
      ],
    }),
  );
  assert.equal(result.status, "PARTIAL");
  assert.equal(result.written, true);
  assert.equal(result.invoiceRecordId, "7001");
  assert.deepEqual(
    result.bills.map((item) => [item.billId, item.status]),
    [
      ["9001", "UPDATED"],
      ["9002", "FAILED"],
      ["9003", "NOT_ATTEMPTED"],
    ],
  );
  assert.equal(writes.submitted.length, 1);
});

test("回读核实不到关联记录时标为部分完成，不当作成功", () => {
  const result = service({}, { dropLinks: true }).api.post(request());
  assert.equal(result.status, "PARTIAL");
  assert.equal(result.bills[0].verified, false);
});

test("主记录保存失败或额度不足时明确未写入", () => {
  const failed = service({}, { failCreate: true }).api.post(request());
  assert.equal(failed.complete, false);
  assert.equal(failed.written, false);
  assert.deepEqual(failed.error, { code: "WRITE_FAILED" });
  assert.ok(!JSON.stringify(failed).includes("save failed"));
  const limited = service({}, { usage: 100 }).api.post(request());
  assert.equal(limited.error.code, "QUERY_LIMIT");
  assert.equal(limited.written, false);
});

test("无效请求在检索和写入前拒绝", () => {
  const base = request();
  for (const input of [
    null,
    { ...base, action: "bills" },
    { ...base, requestId: "not-a-uuid" },
    { ...base, vendorId: "088" },
    { ...base, extra: true },
    { ...base, invoice: { ...base.invoice, number: " INV" } },
    { ...base, invoice: { ...base.invoice, date: "2026-02-30" } },
    { ...base, invoice: { ...base.invoice, amount: "300" } },
    { ...base, invoice: { ...base.invoice, amount: "299.99" } },
    { ...base, bills: [] },
    { ...base, bills: [{ ...base.bills[0], amount: "0.00" }] },
    { ...base, bills: [{ ...base.bills[0], expectedBefore: "-1.00" }] },
    { ...base, bills: [base.bills[0], base.bills[0]] },
    {
      ...base,
      bills: Array.from({ length: 21 }, (_, index) => ({ ...base.bills[0], billId: String(index + 1) })),
    },
  ]) {
    const { api, searches, writes } = service();
    const result = api.post(input);
    assert.equal(result.complete, false, JSON.stringify(input));
    assert.equal(result.error.code, "INVALID_REQUEST");
    assert.equal(result.written, false);
    assert.equal(searches.length + writes.created.length, 0);
  }
});
