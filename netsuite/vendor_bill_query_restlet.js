/**
 * @NApiVersion 2.1
 * @NScriptType Restlet
 * @NModuleScope SameAccount
 */
/* global define */
// 按母单内部 ID 只读查询供应商账单，供回写前对应账单与核对额度。
// 不依赖现网 VendorInvoice.js 的 getData：它跳过税额为 0、可收为 0 和 2025-07-01 以前的账单，
// 查不到时无法区分“账单未生成”和“已登记满”。额度口径与其 handleJson 相同，但用整数分精确计算。
define(["N/search", "N/runtime", "N/log"], (search, runtime, log) => {
  const REVISION = "2026-10-30.4";
  const MAX_ORDERS = 20;
  const MAX_BILLS = 200;
  const MAX_ROWS = 1000;
  // 现网单张账单最多约 10 条有效明细；明细逐行读取后在脚本内合计，上限按账单上限留余量。
  const MAX_DETAILS = 5000;
  const DETAIL = "customrecord_swc_vendor_invoice_detail";
  const INVOICE = "customrecord_swc_vendor_invoice";
  const text = (value) => (value === null || value === undefined ? "" : String(value));
  const id = (input) => typeof input === "string" && /^[1-9][0-9]{0,19}$/.test(input);
  const fail = (code) => {
    throw new Error(code);
  };

  function budget() {
    if (runtime.getCurrentScript().getRemainingUsage() < 150) fail("QUERY_LIMIT");
  }

  function column(label, name, extra = {}) {
    return search.createColumn({ name, label, ...extra });
  }

  function formula(label, expression) {
    return search.createColumn({ name: "formulanumeric", formula: expression, label });
  }

  function rows(type, filters, columns, limit) {
    budget();
    const resultSet = search.create({ type, filters, columns }).run();
    const found = [];
    // getRange 每次最多 1000 行；额外一行用于识别超限，必须分次探测。
    while (found.length <= limit) {
      budget();
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
    return {
      value: (row, label) => text(row.getValue(byLabel.get(label))),
      label: (row, label) => text(row.getText(byLabel.get(label))),
    };
  }

  // 金额统一换成整数分；NS 公式数字可能写成 ".5"，超过两位的非零小数视为异常，不舍入。
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

  function queryInput(input) {
    if (
      !input ||
      typeof input !== "object" ||
      Array.isArray(input) ||
      Object.keys(input).some(
        (key) => !["action", "vendorId", "purchaseOrderIds", "invoiceNumber"].includes(key),
      ) ||
      input.action !== "bills" ||
      !id(input.vendorId) ||
      !Array.isArray(input.purchaseOrderIds) ||
      input.purchaseOrderIds.length === 0 ||
      input.purchaseOrderIds.length > MAX_ORDERS ||
      !input.purchaseOrderIds.every(id) ||
      new Set(input.purchaseOrderIds).size !== input.purchaseOrderIds.length ||
      (Object.prototype.hasOwnProperty.call(input, "invoiceNumber") &&
        (typeof input.invoiceNumber !== "string" ||
          !input.invoiceNumber.length ||
          input.invoiceNumber.length > 100 ||
          input.invoiceNumber !== input.invoiceNumber.trim() ||
          [...input.invoiceNumber].some((char) => char.charCodeAt(0) < 32)))
    )
      fail("INVALID_REQUEST");
    return {
      vendorId: input.vendorId,
      purchaseOrderIds: [...input.purchaseOrderIds],
      ...(Object.prototype.hasOwnProperty.call(input, "invoiceNumber")
        ? { invoiceNumber: input.invoiceNumber }
        : {}),
    };
  }

  function findRegistrations(input) {
    const columns = [column("number", "name"), column("date", "custrecord_swc_vi_billdate")];
    const read = reader(columns);
    const found = rows(
      INVOICE,
      [
        ["name", "is", input.invoiceNumber],
        "AND",
        ["custrecord_swc_vi_vendor", "anyof", input.vendorId],
        "AND",
        ["isinactive", "is", "F"],
      ],
      columns,
      MAX_ROWS,
    );
    const seen = new Set();
    const records = found.map((row) => {
      const record = { id: text(row.id), number: read.value(row, "number"), date: read.value(row, "date") };
      if (!id(record.id) || seen.has(record.id) || record.number !== input.invoiceNumber)
        fail("INVALID_RESULT");
      seen.add(record.id);
      return record;
    });
    return { invoiceNumber: input.invoiceNumber, records };
  }

  function findVendor(vendorId) {
    const columns = [column("code", "entityid"), column("name", "companyname")];
    const read = reader(columns);
    const found = rows(
      "vendor",
      [["internalid", "anyof", vendorId], "AND", ["isinactive", "is", "F"]],
      columns,
      1,
    );
    if (!found.length) return null;
    if (text(found[0].id) !== vendorId) fail("INVALID_RESULT");
    return { id: vendorId, code: read.value(found[0], "code"), name: read.value(found[0], "name") };
  }

  function findOrders(orderIds) {
    const columns = [
      column("number", "tranid"),
      column("vendorId", "entity"),
      column("subsidiaryId", "subsidiary"),
      column("currencyId", "currency"),
    ];
    const read = reader(columns);
    const found = rows(
      "purchaseorder",
      [["internalid", "anyof", orderIds], "AND", ["mainline", "is", "T"]],
      columns,
      orderIds.length,
    );
    const orders = new Map();
    for (const row of found) {
      const order = {
        id: text(row.id),
        number: read.value(row, "number"),
        vendorId: read.value(row, "vendorId"),
        subsidiaryId: read.value(row, "subsidiaryId"),
        currencyId: read.value(row, "currencyId"),
        currencyName: read.label(row, "currencyId"),
      };
      if (
        !orderIds.includes(order.id) ||
        orders.has(order.id) ||
        !order.number ||
        !id(order.vendorId) ||
        !id(order.subsidiaryId) ||
        !id(order.currencyId)
      )
        fail("INVALID_RESULT");
      orders.set(order.id, order);
    }
    return orders;
  }

  // 主行带“核销交易”联接，一张账单按核销交易展开成多行；贷项不计入应收，与平台 handleJson 一致。
  function findBills(orderIds) {
    const columns = [
      column("billNumber", "transactionnumber"),
      column("vendorId", "entity"),
      column("purchaseOrderId", "createdfrom"),
      column("subPurchaseOrderId", "custbody_swc_bill_created_subpo"),
      column("subsidiaryId", "subsidiary"),
      column("currencyId", "currency"),
      column("approvalStatus", "approvalstatus"),
      formula("taxTotal", "NVL({taxtotal}, 0)"),
      formula("remaining", "NVL({amountremaining}, 0)"),
      formula("received", "NVL({custbody_swc_vendor_amount}, 0)"),
      column("applyingType", "type", { join: "applyingTransaction" }),
      formula("applied", "NVL({applyinglinkamount}, 0)"),
    ];
    const read = reader(columns);
    const found = rows(
      "vendorbill",
      [
        ["type", "anyof", "VendBill"],
        "AND",
        ["mainline", "is", "T"],
        "AND",
        ["createdfrom", "anyof", orderIds],
      ],
      columns,
      MAX_ROWS,
    );
    const bills = new Map();
    for (const row of found) {
      const billId = text(row.id);
      const bill = {
        billId,
        billNumber: read.value(row, "billNumber"),
        vendorId: read.value(row, "vendorId"),
        purchaseOrderId: read.value(row, "purchaseOrderId"),
        subPurchaseOrderId: read.value(row, "subPurchaseOrderId"),
        subsidiaryId: read.value(row, "subsidiaryId"),
        currencyId: read.value(row, "currencyId"),
        currencyName: read.label(row, "currencyId"),
        approvalStatus: read.value(row, "approvalStatus"),
        hasTax: cents(read.value(row, "taxTotal")) !== 0,
        remaining: cents(read.value(row, "remaining")),
        received: cents(read.value(row, "received")),
      };
      if (
        !id(billId) ||
        !bill.billNumber ||
        !id(bill.vendorId) ||
        !orderIds.includes(bill.purchaseOrderId) ||
        (bill.subPurchaseOrderId && !id(bill.subPurchaseOrderId)) ||
        !id(bill.subsidiaryId) ||
        !id(bill.currencyId) ||
        !["", "1", "2", "3"].includes(bill.approvalStatus)
      )
        fail("INVALID_RESULT");
      const current = bills.get(billId);
      // 同一账单的展开行，主行字段必须一致，否则说明检索结果不可信。
      if (current && Object.keys(bill).some((key) => current[key] !== bill[key])) fail("INVALID_RESULT");
      const target = current || { ...bill, applied: 0 };
      if (read.value(row, "applyingType") !== "VendCred") target.applied += cents(read.value(row, "applied"));
      bills.set(billId, target);
    }
    if (bills.size > MAX_BILLS) fail("QUERY_LIMIT");
    return bills;
  }

  // NS 检索不允许把 voided 作为结果列（SSS_INVALID_SRCH_COL），只能作为筛选条件，故单独查出已作废账单。
  function findVoided(orderIds) {
    const found = rows(
      "vendorbill",
      [
        ["type", "anyof", "VendBill"],
        "AND",
        ["mainline", "is", "T"],
        "AND",
        ["createdfrom", "anyof", orderIds],
        "AND",
        ["voided", "is", "T"],
      ],
      [column("billId", "internalid")],
      MAX_BILLS,
    );
    return new Set(found.map((row) => text(row.id)));
  }

  // 账单累计金额应等于有效明细“本次收”合计；不一致的账单回写时须先由财务处理。
  // 明细的账单字段不能按 GROUP 汇总（INVALID_RESULT_SUMMARY_FUNC），逐行读取后按整数分合计。
  function findDetails(billIds) {
    if (!billIds.length) return new Map();
    const columns = [
      column("billId", "custrecord_swc_vid_bill"),
      column("amount", "custrecord_swc_cid_current_amount"),
    ];
    const read = reader(columns);
    const found = rows(
      DETAIL,
      [["custrecord_swc_vid_bill", "anyof", billIds], "AND", ["isinactive", "is", "F"]],
      columns,
      MAX_DETAILS,
    );
    const details = new Map();
    for (const row of found) {
      const billId = read.value(row, "billId");
      if (!billIds.includes(billId)) fail("INVALID_RESULT");
      const current = details.get(billId) || { count: 0, total: 0 };
      // 与 SUM 口径一致：未填“本次收”的明细按 0 计入，但仍计入条数。
      current.count += 1;
      current.total += cents(read.value(row, "amount") || "0");
      details.set(billId, current);
    }
    return details;
  }

  function output(bill, voided, detail) {
    const payable = bill.remaining + bill.applied;
    const details = detail || { count: 0, total: 0 };
    return {
      billId: bill.billId,
      billNumber: bill.billNumber,
      vendorId: bill.vendorId,
      purchaseOrderId: bill.purchaseOrderId,
      subPurchaseOrderId: bill.subPurchaseOrderId,
      subsidiaryId: bill.subsidiaryId,
      currencyId: bill.currencyId,
      currencyName: bill.currencyName,
      approvalStatus: bill.approvalStatus,
      voided,
      hasTax: bill.hasTax,
      amounts: {
        remaining: money(bill.remaining),
        applied: money(bill.applied),
        payable: money(payable),
        received: money(bill.received),
        available: money(payable - bill.received),
      },
      details: { count: details.count, total: money(details.total) },
      consistent: details.total === bill.received,
    };
  }

  function query(input, trace) {
    trace.stage = "existing_invoice_lookup";
    const registration = input.invoiceNumber ? { registrationCheck: findRegistrations(input) } : {};
    trace.stage = "vendor_lookup";
    const vendor = findVendor(input.vendorId);
    if (!vendor) return { status: "VENDOR_NOT_FOUND", vendor: null, purchaseOrders: [], ...registration };
    trace.stage = "purchase_order_lookup";
    const orders = findOrders(input.purchaseOrderIds);
    const matched = input.purchaseOrderIds.filter((key) => orders.get(key)?.vendorId === vendor.id);
    trace.stage = "bill_lookup";
    const bills = matched.length ? findBills(matched) : new Map();
    trace.stage = "voided_lookup";
    const voided = bills.size ? findVoided(matched) : new Set();
    if ([...voided].some((billId) => !bills.has(billId))) fail("INVALID_RESULT");
    trace.stage = "invoice_detail_lookup";
    const details = findDetails([...bills.keys()]);
    trace.stage = "result_assembly";
    const purchaseOrders = input.purchaseOrderIds.map((key) => {
      const order = orders.get(key);
      if (!order) return { id: key, status: "PO_NOT_FOUND", bills: [] };
      if (order.vendorId !== vendor.id) return { ...order, status: "VENDOR_MISMATCH", bills: [] };
      const found = [...bills.values()]
        .filter((bill) => bill.purchaseOrderId === key)
        .sort((left, right) => Number(left.billId) - Number(right.billId))
        .map((bill) => output(bill, voided.has(bill.billId), details.get(bill.billId)));
      return { ...order, status: found.length ? "FOUND" : "NO_BILLS", bills: found };
    });
    return { status: "OK", vendor, purchaseOrders, ...registration };
  }

  function post(input) {
    const started = Date.now();
    const trace = { revision: REVISION, stage: "request_validation" };
    const envelope = {
      contractVersion: 3,
      source: "vendor-bill-query",
      account: text(runtime.accountId).toLowerCase().replace(/_/g, "-"),
      readStartedAt: new Date().toISOString(),
    };
    try {
      const request = queryInput(input);
      // 仅记录通过格式校验的身份；不记录原始请求、认证信息或整份业务响应。
      trace.vendorId = request.vendorId;
      trace.purchaseOrderIds = request.purchaseOrderIds;
      const result = query(request, trace);
      trace.stage = "budget_check";
      budget();
      log.audit({
        title: "VENDOR_BILL_QUERY_OK",
        details: JSON.stringify({
          ...trace,
          stage: "complete",
          status: result.status,
          billCount: result.purchaseOrders.reduce((count, order) => count + order.bills.length, 0),
          elapsedMs: Date.now() - started,
        }),
      });
      return {
        ...envelope,
        complete: true,
        query: request,
        ...result,
        readCompletedAt: new Date().toISOString(),
      };
    } catch (error) {
      const message = text(error?.message);
      const code = ["INVALID_REQUEST", "INVALID_RESULT", "QUERY_LIMIT"].includes(message)
        ? message
        : "QUERY_FAILED";
      // 诊断信息仅写入 NS 执行日志，接口仍只返回固定错误码。
      log.error({
        title: "VENDOR_BILL_QUERY_FAILED",
        details: JSON.stringify({
          ...trace,
          code,
          errorName: text(error?.name).slice(0, 100),
          message: message.slice(0, 1000),
          stack: text(error?.stack).slice(0, 2000),
          elapsedMs: Date.now() - started,
        }),
      });
      return { ...envelope, complete: false, error: { code }, readCompletedAt: new Date().toISOString() };
    }
  }

  return { post };
});
