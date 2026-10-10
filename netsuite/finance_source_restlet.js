/**
 * @NApiVersion 2.1
 * @NScriptType Restlet
 * @NModuleScope SameAccount
 */
/* global define */
// 只读报关头的原始子行，不依赖未暴露到 REST / SuiteQL 的子记录类型名称。
define(["N/record", "N/runtime"], (record, runtime) => {
  const SUBLIST = "recmachcustrecord_swc_sl_relate";
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

  function post(input) {
    if (
      !input ||
      typeof input !== "object" ||
      Array.isArray(input) ||
      Object.keys(input).some((key) => key !== "declarationIds") ||
      !ids(input.declarationIds)
    ) {
      return {
        complete: false,
        error: { code: "INVALID_INPUT", message: "仅接受1至20个不同的报关内部ID。" },
      };
    }
    const declarations = [];
    let total = 0;
    try {
      for (const id of input.declarationIds) {
        if (runtime.getCurrentScript().getRemainingUsage() < 100) {
          return {
            complete: false,
            error: { code: "QUERY_LIMIT", message: "查询额度不足，请缩小单据范围。" },
          };
        }
        const header = record.load({ type: "customrecord_swc_declare_record", id, isDynamic: false });
        const sublists = header.getSublists();
        if (!sublists.includes(SUBLIST)) {
          return {
            complete: false,
            error: {
              code: "RAW_SUBLIST_UNAVAILABLE",
              message: "当前身份无法读取报关原始子行，请核实记录权限。",
            },
          };
        }
        const available = header.getSublistFields({ sublistId: SUBLIST });
        const identityField = available.includes("id")
          ? "id"
          : available.includes("internalid")
            ? "internalid"
            : "";
        const missingFields = Object.values(FIELDS).filter((field) => !available.includes(field));
        if (!identityField || missingFields.length) {
          return {
            complete: false,
            error: { code: "RAW_FIELDS_UNAVAILABLE", message: "原始行身份或来源字段不完整。", missingFields },
          };
        }
        const count = header.getLineCount({ sublistId: SUBLIST });
        total += count;
        if (!Number.isInteger(count) || count < 0 || total > 2000) {
          return { complete: false, error: { code: "QUERY_LIMIT", message: "原始行超过读取上限。" } };
        }
        const rows = [];
        const seen = new Set();
        for (let line = 0; line < count; line++) {
          const get = (fieldId) => text(header.getSublistValue({ sublistId: SUBLIST, fieldId, line }));
          const sourceId = get(identityField);
          if (!/^[1-9][0-9]*$/.test(sourceId) || seen.has(sourceId)) {
            return {
              complete: false,
              error: { code: "INVALID_SOURCE_ID", message: "原始行缺少唯一来源身份。" },
            };
          }
          seen.add(sourceId);
          rows.push({
            id: sourceId,
            declarationId: id,
            ...Object.fromEntries(Object.entries(FIELDS).map(([key, field]) => [key, get(field)])),
          });
        }
        declarations.push({ id, recordNumber: text(header.getValue({ fieldId: "name" })), rows });
      }
      return {
        contractVersion: 1,
        complete: true,
        account: text(runtime.accountId).toLowerCase().replace(/_/g, "-"),
        declarations,
      };
    } catch {
      // 不回显 NS 原始异常、记录正文或调用堆栈；失败不返回已读取的部分单据。
      return {
        complete: false,
        error: { code: "SOURCE_READ_FAILED", message: "报关来源读取失败，请核实当前身份的读取权限。" },
      };
    }
  }
  return { post };
});
