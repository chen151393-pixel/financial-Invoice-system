/**
 * @NApiVersion 2.1
 * @NScriptType Restlet
 * @NModuleScope SameAccount
 */
/* global define */
// 发票登记到 NS 现有“供应商开票平台”结构：一张发票一条主记录，每张账单一行明细，并更新账单累计金额与关联记录。
// 首期简化口径（docs/ns-invoice-writeback-plan.md 第 1.1 节）：不建 NS 请求账本和唯一键；
// 写前按“发票号码＋供应商”只读查一次已有记录，并要求账单累计等于调用方冻结的写前值，任一不符整单不写。
// 账单读取口径与 vendor_bill_query_restlet.js 相同；两个脚本独立部署，故各自保留检索代码。
define(["N/search", "N/record", "N/runtime", "N/log"], (search, record, runtime, log) => {
  const REVISION = "2026-10-29.1";
  const MAX_BILLS = 20;
  const MAX_ROWS = 1000;
  const INVOICE = "customrecord_swc_vendor_invoice";
  const SUBLIST = "recmachcustrecord_swc_vid_main";
  const FIELDS = {
    invoiceDate: "custrecord_swc_vi_billdate",
    invoiceVendor: "custrecord_swc_vi_vendor",
    detailBill: "custrecord_swc_vid_bill",
    detailOrder: "custrecord_swc_vid_po",
    detailPayable: "custrecord_swc_vid_billamount",
    detailBefore: "custrecord_swc_vid_billpaied",
    detailAmount: "custrecord_swc_cid_current_amount",
    billReceived: "custbody_swc_vendor_amount",
    billInvoices: "custbody_swc_bill_vendor_num",
  };
  const text = (value) => (value === null || value === undefined ? "" : String(value));
  const id = (input) => typeof input === "string" && /^[1-9][0-9]{0,19}$/.test(input);
  const decimal = (input) => typeof input === "string" && /^(?:0|[1-9][0-9]{0,15})\.[0-9]{2}$/.test(input);
  const fail = (code) => {
    throw new Error(code);
  };
  // 发票号码原样作为主记录名称：首尾无空白、无控制字符、最多 100 字。
  const invoiceNumber = (value) =>
    typeof value === "string" &&
    value.length > 0 &&
    value.length <= 100 &&
    value === value.trim() &&
    [...value].every((char) => char.charCodeAt(0) >= 32);

  function budget(required) {
    if (runtime.getCurrentScript().getRemainingUsage() < required) fail("QUERY_LIMIT");
  }

  function column(label, name, extra = {}) {
    return search.createColumn({ name, label, ...extra });
  }

  function formula(label, expression) {
    return search.createColumn({ name: "formulanumeric", formula: expression, label });
  }

  function rows(type, filters, columns, limit) {
    budget(150);
    const resultSet = search.create({ type, filters, columns }).run();
    const found = [];
    // 多读一条检测超量，但每次最多读取 1000 条（与只读查询脚本保持一致）。
    while (found.length <= limit) {
      budget(150);
      const start = found.length;
      const end = Math.min(start + 1000, limit + 1);
      const page = resultSet.getRange({ start, end });
      found.push(...page);
      if (page.length < end - start) break;
    }
    if (found.length > limit) fail("QUERY_LIMIT");
    return found;
  }

  function reader(columns) {
    const byLabel = new Map(columns.map((item) => [item.label, item]));
    return { value: (row, label) => text(row.getValue(byLabel.get(label))) };
  }

  // 金额统一换成整数分，超过两位的非零小数视为异常，不舍入。
  function cents(input) {
    const match = /^(-?)(\d*)(?:\.(\d+))?$/.exec(text(input).trim());
    if (!match || (!match[2] && !match[3])) fail("INVALID_RESULT");
    const fraction = (match[3] || "").replace(/0+$/, "");
    if (fraction.length > 2) fail("INVALID_RESULT");
    const whole = Number(match[2] || "0");
    const value = whole * 100 + Number(fraction.padEnd(2, "0"));
    if (!Number.isSafeInteger(value) || whole > 1e12) fail("INVALID_RESULT");
    return match[1] && value ? -value : value;
  }

  function money(value) {
    const sign = value < 0 ? "-" : "";
    const absolute = Math.abs(value);
    return `${sign}${Math.floor(absolute / 100)}.${String(absolute % 100).padStart(2, "0")}`;
  }

  // NS 日期字段按脚本时区的本地日期保存，不能用 UTC 解析，否则可能差一天。
  function localDate(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (!match) return null;
    const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
    return date.getFullYear() === Number(match[1]) &&
      date.getMonth() === Number(match[2]) - 1 &&
      date.getDate() === Number(match[3])
      ? date
      : null;
  }

  function applyInput(input) {
    const keys = (value, allowed) =>
      value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      Object.keys(value).every((key) => allowed.includes(key));
    if (
      !keys(input, ["action", "requestId", "vendorId", "invoice", "bills"]) ||
      input.action !== "apply" ||
      typeof input.requestId !== "string" ||
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(input.requestId) ||
      !id(input.vendorId) ||
      !keys(input.invoice, ["number", "date", "amount"]) ||
      !invoiceNumber(input.invoice.number) ||
      typeof input.invoice.date !== "string" ||
      !localDate(input.invoice.date) ||
      !decimal(input.invoice.amount) ||
      !Array.isArray(input.bills) ||
      input.bills.length === 0 ||
      input.bills.length > MAX_BILLS ||
      !input.bills.every(
        (line) =>
          keys(line, ["billId", "purchaseOrderId", "amount", "expectedBefore"]) &&
          id(line.billId) &&
          id(line.purchaseOrderId) &&
          decimal(line.amount) &&
          cents(line.amount) > 0 &&
          decimal(line.expectedBefore),
      ) ||
      new Set(input.bills.map((line) => line.billId)).size !== input.bills.length ||
      input.bills.reduce((sum, line) => sum + cents(line.amount), 0) !== cents(input.invoice.amount)
    )
      fail("INVALID_REQUEST");
    return {
      requestId: input.requestId,
      vendorId: input.vendorId,
      invoice: { ...input.invoice },
      bills: input.bills.map((line) => ({ ...line })),
    };
  }

  // 同号发票只读检查一次；不是并发唯一保证，查到即停下交人工核对。
  function findExisting(request) {
    const columns = [column("name", "name"), column("date", FIELDS.invoiceDate)];
    const read = reader(columns);
    return rows(
      INVOICE,
      [
        ["name", "is", request.invoice.number],
        "AND",
        [FIELDS.invoiceVendor, "anyof", request.vendorId],
        "AND",
        ["isinactive", "is", "F"],
      ],
      columns,
      MAX_ROWS,
    ).map((row) => ({ id: text(row.id), number: read.value(row, "name"), date: read.value(row, "date") }));
  }

  // 主行带“核销交易”联接，一张账单按核销交易展开成多行；贷项不计入应收，与查询脚本一致。
  function findBills(billIds) {
    const columns = [
      column("billNumber", "transactionnumber"),
      column("vendorId", "entity"),
      column("purchaseOrderId", "createdfrom"),
      column("approvalStatus", "approvalstatus"),
      formula("remaining", "NVL({amountremaining}, 0)"),
      formula("received", `NVL({${FIELDS.billReceived}}, 0)`),
      column("invoices", FIELDS.billInvoices),
      column("applyingType", "type", { join: "applyingTransaction" }),
      formula("applied", "NVL({applyinglinkamount}, 0)"),
    ];
    const read = reader(columns);
    const filters = [
      ["type", "anyof", "VendBill"],
      "AND",
      ["mainline", "is", "T"],
      "AND",
      ["internalid", "anyof", billIds],
    ];
    const bills = new Map();
    for (const row of rows("vendorbill", filters, columns, MAX_ROWS)) {
      const billId = text(row.id);
      const bill = {
        billId,
        billNumber: read.value(row, "billNumber"),
        vendorId: read.value(row, "vendorId"),
        purchaseOrderId: read.value(row, "purchaseOrderId"),
        approvalStatus: read.value(row, "approvalStatus"),
        remaining: cents(read.value(row, "remaining")),
        received: cents(read.value(row, "received")),
        invoices: read.value(row, "invoices"),
      };
      if (!billIds.includes(billId)) fail("INVALID_RESULT");
      const current = bills.get(billId);
      if (current && Object.keys(bill).some((key) => current[key] !== bill[key])) fail("INVALID_RESULT");
      const target = current || { ...bill, applied: 0 };
      if (read.value(row, "applyingType") !== "VendCred") target.applied += cents(read.value(row, "applied"));
      bills.set(billId, target);
    }
    // voided 只能作为筛选条件，不能作为结果列。
    const voided = new Set(
      rows(
        "vendorbill",
        [...filters, "AND", ["voided", "is", "T"]],
        [column("billId", "internalid")],
        MAX_BILLS,
      ).map((row) => text(row.id)),
    );
    return { bills, voided };
  }

  function problems(request, found) {
    const result = [];
    for (const line of request.bills) {
      const bill = found.bills.get(line.billId);
      const problem = (code) => result.push({ billId: line.billId, code });
      if (!bill) {
        problem("BILL_NOT_FOUND");
        continue;
      }
      if (bill.vendorId !== request.vendorId) problem("VENDOR_MISMATCH");
      if (bill.purchaseOrderId !== line.purchaseOrderId) problem("ORDER_MISMATCH");
      if (bill.approvalStatus !== "2") problem("NOT_APPROVED");
      if (found.voided.has(line.billId)) problem("VOIDED");
      // 账单累计已在冻结预览后变化：可能其他发票已登记到同一账单，须重新查询并确认。
      if (bill.received !== cents(line.expectedBefore)) problem("STALE");
      if (cents(line.amount) > bill.remaining + bill.applied - bill.received) problem("OVER_AVAILABLE");
    }
    return result;
  }

  function createInvoice(request, found) {
    const invoice = record.create({ type: INVOICE });
    invoice.setValue({ fieldId: "name", value: request.invoice.number });
    invoice.setValue({ fieldId: FIELDS.invoiceDate, value: localDate(request.invoice.date) });
    invoice.setValue({ fieldId: FIELDS.invoiceVendor, value: request.vendorId });
    request.bills.forEach((line, index) => {
      const bill = found.bills.get(line.billId);
      const values = {
        [FIELDS.detailBill]: line.billId,
        [FIELDS.detailOrder]: line.purchaseOrderId,
        [FIELDS.detailPayable]: Number(money(bill.remaining + bill.applied)),
        [FIELDS.detailBefore]: Number(money(bill.received)),
        [FIELDS.detailAmount]: Number(line.amount),
      };
      for (const [fieldId, value] of Object.entries(values))
        invoice.setSublistValue({ sublistId: SUBLIST, fieldId, line: index, value });
    });
    return text(invoice.save({ enableSourcing: false, ignoreMandatoryFields: false }));
  }

  // 写后累计 = 写前累计 ＋ 本次金额；不按明细重算，不改动历史差异。
  function updateBill(line, bill, invoiceId) {
    const after = bill.received + cents(line.amount);
    const linked = bill.invoices
      ? bill.invoices
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean)
      : [];
    record.submitFields({
      type: record.Type.VENDOR_BILL,
      id: line.billId,
      values: {
        [FIELDS.billReceived]: Number(money(after)),
        [FIELDS.billInvoices]: [...new Set([...linked, invoiceId])],
      },
      options: { enableSourcing: false, ignoreMandatoryFields: true },
    });
    const saved = search.lookupFields({
      type: search.Type.VENDOR_BILL,
      id: line.billId,
      columns: [FIELDS.billReceived, FIELDS.billInvoices],
    });
    const savedLinks = [].concat(saved[FIELDS.billInvoices] || []).map((item) => text(item && item.value));
    return {
      billId: line.billId,
      billNumber: bill.billNumber,
      status: "UPDATED",
      before: money(bill.received),
      amount: line.amount,
      after: money(after),
      verified: cents(saved[FIELDS.billReceived] || "0") === after && savedLinks.includes(invoiceId),
    };
  }

  function apply(request, trace) {
    trace.stage = "duplicate_check";
    const existing = findExisting(request);
    if (existing.length) return { status: "CONFLICT", written: false, existing };
    trace.stage = "bill_check";
    const found = findBills(request.bills.map((line) => line.billId));
    const rejected = problems(request, found);
    if (rejected.length) return { status: "REJECTED", written: false, problems: rejected };
    // 写入前留足整单所需额度，避免主记录建好后账单更新因额度中断。
    budget(200 + request.bills.length * 30);
    trace.stage = "invoice_create";
    const invoiceId = createInvoice(request, found);
    trace.invoiceId = invoiceId;
    const bills = [];
    let failed = false;
    for (const line of request.bills) {
      const bill = found.bills.get(line.billId);
      if (failed) {
        bills.push({
          billId: line.billId,
          billNumber: bill.billNumber,
          status: "NOT_ATTEMPTED",
          amount: line.amount,
        });
        continue;
      }
      trace.stage = `bill_update:${line.billId}`;
      try {
        budget(50);
        bills.push(updateBill(line, bill, invoiceId));
      } catch (error) {
        // 主记录已建成：不回滚、不重试，逐张标明结果交人工核实。
        failed = true;
        trace.failure = text(error && error.message).slice(0, 500);
        bills.push({
          billId: line.billId,
          billNumber: bill.billNumber,
          status: "FAILED",
          amount: line.amount,
        });
      }
    }
    const complete = !failed && bills.every((item) => item.verified);
    return { status: complete ? "APPLIED" : "PARTIAL", written: true, invoiceRecordId: invoiceId, bills };
  }

  function post(input) {
    const started = Date.now();
    const trace = { revision: REVISION, stage: "request_validation" };
    const envelope = {
      contractVersion: 1,
      source: "vendor-bill-writeback",
      account: text(runtime.accountId).toLowerCase().replace(/_/g, "-"),
      startedAt: new Date().toISOString(),
    };
    let request = null;
    try {
      request = applyInput(input);
      trace.requestId = request.requestId;
      trace.vendorId = request.vendorId;
      trace.billIds = request.bills.map((line) => line.billId);
      const result = apply(request, trace);
      log.audit({
        title: "VENDOR_BILL_WRITEBACK",
        details: JSON.stringify({ ...trace, status: result.status, elapsedMs: Date.now() - started }),
      });
      return {
        ...envelope,
        complete: true,
        requestId: request.requestId,
        ...result,
        completedAt: new Date().toISOString(),
      };
    } catch (error) {
      const message = text(error && error.message);
      const code = ["INVALID_REQUEST", "INVALID_RESULT", "QUERY_LIMIT"].includes(message)
        ? message
        : "WRITE_FAILED";
      // 抛到这里时尚未建成主记录（建成后的账单错误在 apply 内逐张处理），可确认未写入。
      const written = Boolean(trace.invoiceId);
      log.error({
        title: "VENDOR_BILL_WRITEBACK_FAILED",
        details: JSON.stringify({
          ...trace,
          code,
          errorName: text(error && error.name).slice(0, 100),
          message: message.slice(0, 1000),
          elapsedMs: Date.now() - started,
        }),
      });
      return {
        ...envelope,
        complete: false,
        requestId: request ? request.requestId : null,
        written,
        ...(written ? { invoiceRecordId: trace.invoiceId } : {}),
        error: { code },
        completedAt: new Date().toISOString(),
      };
    }
  }

  return { post };
});
