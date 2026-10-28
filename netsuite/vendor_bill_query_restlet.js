/**
 * @NApiVersion 2.1
 * @NScriptType Restlet
 * @NModuleScope SameAccount
 */
/* global define */
// 按母单内部 ID 只读查询供应商账单，供回写前对应账单与核对额度。
// 不依赖现网 VendorInvoice.js 的 getData：它跳过税额为 0、可收为 0 和 2025-07-01 以前的账单，
// 查不到时无法区分“账单未生成”和“已登记满”。额度口径与其 handleJson 相同，但用整数分精确计算。
define(["N/search", "N/runtime"], (search, runtime) => {
  const MAX_ORDERS = 20;
  const MAX_BILLS = 200;
  const MAX_ROWS = 1000;
  const DETAIL = "customrecord_swc_vendor_invoice_detail";
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
    const found = search
      .create({ type, filters, columns })
      .run()
      .getRange({ start: 0, end: limit + 1 });
    if (found.length > limit) fail("QUERY_LIMIT");
    return found;
  }

  function reader(columns) {
    const byLabel = new Map(columns.map((item) => [item.label, item]));
    return {
      raw: (row, label) => row.getValue(byLabel.get(label)),
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

  function flag(value) {
    if (value === true || value === "T") return true;
    if (value === false || value === "F" || value === "") return false;
    return fail("INVALID_RESULT");
  }

  function queryInput(input) {
    if (
      !input ||
      typeof input !== "object" ||
      Array.isArray(input) ||
      Object.keys(input).some((key) => !["action", "vendorId", "purchaseOrderIds"].includes(key)) ||
      input.action !== "bills" ||
      !id(input.vendorId) ||
      !Array.isArray(input.purchaseOrderIds) ||
      input.purchaseOrderIds.length === 0 ||
      input.purchaseOrderIds.length > MAX_ORDERS ||
      !input.purchaseOrderIds.every(id) ||
      new Set(input.purchaseOrderIds).size !== input.purchaseOrderIds.length
    )
      fail("INVALID_REQUEST");
    return { vendorId: input.vendorId, purchaseOrderIds: [...input.purchaseOrderIds] };
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
      column("voided", "voided"),
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
        voided: flag(read.raw(row, "voided")),
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

  // 账单累计金额应等于有效明细“本次收”合计；不一致的账单回写时须先由财务处理。
  function findDetails(billIds) {
    if (!billIds.length) return new Map();
    const columns = [
      column("billId", "custrecord_swc_vid_bill", { summary: search.Summary.GROUP }),
      column("total", "custrecord_swc_cid_current_amount", { summary: search.Summary.SUM }),
      column("count", "internalid", { summary: search.Summary.COUNT }),
    ];
    const read = reader(columns);
    const found = rows(
      DETAIL,
      [["custrecord_swc_vid_bill", "anyof", billIds], "AND", ["isinactive", "is", "F"]],
      columns,
      billIds.length,
    );
    const details = new Map();
    for (const row of found) {
      const billId = read.value(row, "billId");
      const count = Number(read.value(row, "count"));
      if (!billIds.includes(billId) || details.has(billId) || !Number.isSafeInteger(count) || count < 1)
        fail("INVALID_RESULT");
      details.set(billId, { count, total: cents(read.value(row, "total") || "0") });
    }
    return details;
  }

  function output(bill, detail) {
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
      voided: bill.voided,
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

  function query(input) {
    const vendor = findVendor(input.vendorId);
    if (!vendor) return { status: "VENDOR_NOT_FOUND", vendor: null, purchaseOrders: [] };
    const orders = findOrders(input.purchaseOrderIds);
    const matched = input.purchaseOrderIds.filter((key) => orders.get(key)?.vendorId === vendor.id);
    const bills = matched.length ? findBills(matched) : new Map();
    const details = findDetails([...bills.keys()]);
    const purchaseOrders = input.purchaseOrderIds.map((key) => {
      const order = orders.get(key);
      if (!order) return { id: key, status: "PO_NOT_FOUND", bills: [] };
      if (order.vendorId !== vendor.id) return { ...order, status: "VENDOR_MISMATCH", bills: [] };
      const found = [...bills.values()]
        .filter((bill) => bill.purchaseOrderId === key)
        .sort((left, right) => Number(left.billId) - Number(right.billId))
        .map((bill) => output(bill, details.get(bill.billId)));
      return { ...order, status: found.length ? "FOUND" : "NO_BILLS", bills: found };
    });
    return { status: "OK", vendor, purchaseOrders };
  }

  function post(input) {
    const envelope = {
      contractVersion: 3,
      source: "vendor-bill-query",
      account: text(runtime.accountId).toLowerCase().replace(/_/g, "-"),
      readStartedAt: new Date().toISOString(),
    };
    try {
      const request = queryInput(input);
      const result = query(request);
      budget();
      return {
        ...envelope,
        complete: true,
        query: request,
        ...result,
        readCompletedAt: new Date().toISOString(),
      };
    } catch (error) {
      const code = ["INVALID_REQUEST", "INVALID_RESULT", "QUERY_LIMIT"].includes(error.message)
        ? error.message
        : "QUERY_FAILED";
      return { ...envelope, complete: false, error: { code }, readCompletedAt: new Date().toISOString() };
    }
  }

  return { post };
});
