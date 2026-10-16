/**
 * @NApiVersion 2.1
 * @NScriptType Restlet
 * @NModuleScope SameAccount
 */
/* global define */
// 只读报关头的原始子行，不依赖未暴露到 REST / SuiteQL 的子记录类型名称。
define(["N/record", "N/runtime"], (record, runtime) => {
  const SUBLIST = "recmachcustrecord_swc_sl_relate";
  const SUBLIST_PARAMETER = "custscript_fin_source_sublist";
  const RECORD_TYPE = "customrecord_swc_declare_record";
  const FIELDS = {
    plId: "custrecord_swc_packing_main",
    packingId: "custrecord_swc_packinglist",
    companyId: "custrecord_swc_declare_company",
    fulfillmentId: "custrecord_swc_fulfillment_id",
    fulfillmentLine: "custrecord_swc_fulfillment_line",
    itemId: "custrecord_swc_declare_item",
    name: "custrecord_details_item_name",
    sourceQuantity: "custrecord_swc_packingqty_2",
    declarationQuantity: "custrecord_swc_details_packingqty",
    declarationUnitId: "custrecord_swc_details_unit",
    declarationModel: "custrecord_swc_details_model",
    parentPurchaseId: "custrecord_swc_detail_purchase",
  };
  const text = (value) => (value === null || value === undefined ? "" : String(value));
  const ids = (values) =>
    Array.isArray(values) &&
    values.length > 0 &&
    values.length <= 20 &&
    values.every((value) => typeof value === "string" && /^[1-9][0-9]{0,19}$/.test(value)) &&
    new Set(values).size === values.length;

  // 所有脚本响应使用同一版本与账套标识，调用方仍须先检查 complete。
  const envelope = () => ({
    contractVersion: 1,
    account: text(runtime.accountId).toLowerCase().replace(/_/g, "-"),
  });
  const failure = (code, message, details = {}) => ({
    ...envelope(),
    complete: false,
    error: { code, message, ...details },
  });

  function sourceFields(available) {
    return {
      identityField: available.includes("id") ? "id" : available.includes("internalid") ? "internalid" : "",
      missingFields: Object.values(FIELDS).filter((field) => !available.includes(field)),
    };
  }

  function inspectSublist(header, sublistId) {
    const result = { sublistId, fields: null, lineCount: null, issues: [] };
    try {
      result.fields = header.getSublistFields({ sublistId });
      Object.assign(result, sourceFields(result.fields));
    } catch {
      result.issues.push("FIELDS_READ_FAILED");
    }
    try {
      const count = header.getLineCount({ sublistId });
      if (!Number.isInteger(count) || count < 0) throw new Error("Invalid count");
      result.lineCount = count;
    } catch {
      result.issues.push("LINE_COUNT_READ_FAILED");
    }
    return result;
  }

  // 只输出结构，不读业务字段值；某个子列表不可检查时仍保留其他诊断结果。
  function inspectHeader(header, id, sublistId) {
    const result = { id, expectedSublistId: sublistId, bodyFields: null, sublists: [], issues: [] };
    try {
      result.bodyFields = header.getFields();
    } catch {
      result.issues.push("BODY_FIELDS_READ_FAILED");
    }
    try {
      const visible = header.getSublists();
      result.expectedSublistVisible = visible.includes(sublistId);
      result.sublists = visible.map((value) => inspectSublist(header, value));
    } catch {
      result.issues.push("SUBLISTS_READ_FAILED");
    }
    result.inspectionComplete =
      result.issues.length === 0 && result.sublists.every((item) => item.issues.length === 0);
    return result;
  }

  function diagnose(declarationIds, sublistId) {
    const diagnostics = declarationIds.map((id) => {
      if (runtime.getCurrentScript().getRemainingUsage() < 100) {
        return { id, inspectionComplete: false, issues: ["QUERY_LIMIT"] };
      }
      try {
        const header = record.load({ type: RECORD_TYPE, id, isDynamic: false });
        return inspectHeader(header, id, sublistId);
      } catch {
        return { id, inspectionComplete: false, issues: ["HEADER_LOAD_FAILED"] };
      }
    });
    // 诊断成功也不是业务来源读取成功，避免旧调用方将其用于落库。
    return {
      ...envelope(),
      mode: "diagnose",
      complete: false,
      diagnosticsComplete: diagnostics.every((item) => item.inspectionComplete),
      diagnostics,
    };
  }

  function post(input) {
    if (
      !input ||
      typeof input !== "object" ||
      Array.isArray(input) ||
      Object.keys(input).some((key) => !["declarationIds", "action"].includes(key)) ||
      (Object.prototype.hasOwnProperty.call(input, "action") &&
        !["read", "diagnose"].includes(input.action)) ||
      !ids(input.declarationIds)
    ) {
      return failure(
        "INVALID_INPUT",
        "仅接受1至20个不同的报关内部ID字符串，action可省略或为read、diagnose。",
      );
    }
    const declarations = [];
    // 同一原始行不能属于本次请求的两张报关单；失败时不返回已读取部分。
    const seen = new Set();
    let total = 0;
    try {
      const configured = runtime.getCurrentScript().getParameter({ name: SUBLIST_PARAMETER });
      const sublistId = text(configured).trim() || SUBLIST;
      if (sublistId.length > 200 || !/^recmachcustrecord_[a-z0-9_]+$/i.test(sublistId)) {
        return failure(
          "INVALID_SOURCE_CONFIG",
          "原始子列表部署参数无效，请填写核实后的recmachcustrecord_标识。",
        );
      }
      if (input.action === "diagnose") return diagnose(input.declarationIds, sublistId);
      for (const id of input.declarationIds) {
        if (runtime.getCurrentScript().getRemainingUsage() < 100) {
          return failure("QUERY_LIMIT", "查询额度不足，请缩小单据范围。");
        }
        const header = record.load({ type: RECORD_TYPE, id, isDynamic: false });
        const sublists = header.getSublists();
        if (!sublists.includes(sublistId)) {
          return failure(
            "RAW_SUBLIST_UNAVAILABLE",
            "配置的原始子列表不可见，请根据诊断核实标识、读取路径与角色权限。",
            {
              diagnostic: inspectHeader(header, id, sublistId),
            },
          );
        }
        const available = header.getSublistFields({ sublistId });
        const { identityField, missingFields } = sourceFields(available);
        if (!identityField || missingFields.length) {
          return failure("RAW_FIELDS_UNAVAILABLE", "原始行身份或来源字段不完整。", {
            missingFields,
            identityFieldMissing: !identityField,
            diagnostic: inspectHeader(header, id, sublistId),
          });
        }
        const count = header.getLineCount({ sublistId });
        total += count;
        if (!Number.isInteger(count) || count < 0 || total > 2000) {
          return failure("QUERY_LIMIT", "原始行超过读取上限。");
        }
        const rows = [];
        for (let line = 0; line < count; line++) {
          const get = (fieldId) => text(header.getSublistValue({ sublistId, fieldId, line }));
          const sourceId = get(identityField);
          if (!/^[1-9][0-9]{0,19}$/.test(sourceId) || seen.has(sourceId)) {
            return failure("INVALID_SOURCE_ID", "原始行身份无效或在本次请求中重复。");
          }
          seen.add(sourceId);
          rows.push({
            id: sourceId,
            declarationId: id,
            ...Object.fromEntries(Object.entries(FIELDS).map(([key, field]) => [key, get(field)])),
          });
        }
        const recordNumber = text(header.getValue({ fieldId: "name" }));
        if (!recordNumber.trim()) {
          return failure("HEADER_FIELDS_UNAVAILABLE", "报关记录编号不可读取。");
        }
        declarations.push({ id, recordNumber, rows });
      }
      return {
        ...envelope(),
        complete: true,
        declarations,
      };
    } catch {
      // 不回显 NS 原始异常、记录正文或调用堆栈；失败不返回已读取的部分单据。
      return failure("SOURCE_READ_FAILED", "报关来源读取失败，请核实内部ID、读取路径、角色权限及NS日志。");
    }
  }
  return { post };
});
