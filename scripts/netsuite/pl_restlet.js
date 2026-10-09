/**
 * @NApiVersion 2.1
 * @NScriptType Restlet
 * @NModuleScope SameAccount
 */
/* global define */
// 部署到NS现有pl_lookup目录，与Suitelet引用同一查询服务，仅返回JSON。
// v3接口保留17列原值，增加报关身份、来源行身份及显式父行引用。
define(["./pl_query_service"], (service) => {
  const text = (value) => String(value ?? "");
  function post(input) {
    const keys = ["type", "pl", "month", "createdFrom", "createdTo", "showIncomplete"];
    if (
      !input ||
      typeof input !== "object" ||
      Array.isArray(input) ||
      Object.keys(input).some((key) => !keys.includes(key)) ||
      keys.slice(0, 5).some((key) => input[key] !== undefined && typeof input[key] !== "string") ||
      (input.showIncomplete !== undefined && typeof input.showIncomplete !== "boolean")
    ) {
      return { complete: false, error: { code: "INVALID_INPUT", message: "查询参数格式不正确" } };
    }
    // 旧共用服务缺少报关原单价和币种时明确要求升级，不能返回空列冒充完整结果。
    if (
      !Array.isArray(service.DISPLAY_KEYS) ||
      service.DISPLAY_KEYS.length !== 15 ||
      !Array.isArray(service.TABLE_KEYS) ||
      service.TABLE_KEYS.length !== 17 ||
      service.DISPLAY_KEYS.some((key, index) => service.TABLE_KEYS[index] !== key) ||
      service.TABLE_KEYS[15] !== "customsPrice" ||
      service.TABLE_KEYS[16] !== "customsCurrency"
    ) {
      return {
        complete: false,
        error: {
          code: "SERVICE_VERSION_UNSUPPORTED",
          message: "NS共用查询服务版本不支持17列核对，请管理员更新共用查询脚本后重试。",
        },
      };
    }
    const result = service.query(input, "custscript_pw");
    if (!result.complete || result.error) return result;
    const groups = result.groups.map((group, groupIndex) => {
      const customsIds = [
        ...new Set(group.customsRows.map((row) => text(row.values.parentId)).filter(Boolean)),
      ];
      const declarationId = customsIds.length === 1 ? customsIds[0] : "";
      const header = (result.declarations || []).find((record) => text(record.id) === declarationId);
      const recordNumber = text(header?.recordNumber || /^报关单\s+(CD\S+)$/.exec(group.title || "")?.[1]);
      const reviewIssues = [];
      if (!declarationId || !recordNumber) reviewIssues.push("报关单来源身份不完整");
      if (result.queryType === "pl" && result.queryNumber)
        reviewIssues.push("PL查询可能仅包含部分来源，请按CD编号查询整张报关单后审核");
      if (!result.diagnostics || result.diagnostics.total > 0)
        reviewIssues.push("NS来源追溯仍有待核实项，请按CD编号单独查询并核查NS诊断");
      const order =
        group.displayOrder ||
        ["customs", "purchase"].flatMap((side) => group[`${side}Rows`].map((_, index) => ({ side, index })));
      return {
        id: text(group.key || groupIndex),
        title:
          group.title ||
          `第 ${groupIndex + 1} 组｜${group.pl || "PL未填写"}｜${group.company || "公司待确认"}`,
        customsCount: group.customsRows.length,
        purchaseCount: group.purchaseRows.length,
        warnings: group.warnings,
        declarationId,
        recordNumber,
        plNumbers: text(group.pl),
        company: text(group.company),
        reviewIssues,
        rows: order.map(({ side, index, note, customsIndex }) => {
          const row = group[`${side}Rows`][index];
          return {
            id: `${side}:${index}`,
            side,
            sourceKey: text(row.rowKey),
            customsRowId:
              side === "purchase" && Number.isInteger(customsIndex) && group.customsRows[customsIndex]
                ? `customs:${customsIndex}`
                : null,
            currency: text(row.values.currencyName || row.values.currency),
            note: side === "purchase" ? text(note) : "",
            cells: service.TABLE_KEYS.map((key) => {
              const value = row.values[key];
              if (key === "price" && value == null)
                return side === "purchase" && row.values.amount == null
                  ? ""
                  : row.priceCalculated
                    ? "—"
                    : "待确认";
              if (key === "declaration" && value == null && side === "customs") return "未填写";
              if (key === "parent" && value == null) return "未填写";
              return text(value);
            }),
          };
        }),
      };
    });
    return {
      contractVersion: 3,
      complete: true,
      source: "netsuite-script",
      account: result.account,
      requestId: result.requestId,
      query: {
        type: result.queryType,
        pl: result.queryNumber,
        month: result.queryMonth,
        createdFrom: result.queryCreatedFrom,
        createdTo: result.queryCreatedTo,
        showIncomplete: result.showIncomplete,
      },
      readStartedAt: result.readStartedAt,
      readCompletedAt: result.readCompletedAt,
      elapsedMs: result.elapsedMs,
      monthDateLabel: result.monthDateLabel,
      counts: {
        customs: result.counts.customs,
        purchase: result.counts.purchase,
        groups: result.counts.groups,
        declarations: result.counts.declarations,
      },
      declarations: (result.declarations || []).map((record) =>
        Object.fromEntries(
          ["id", "recordNumber", "declarationNumber", "date", "created"].map((key) => [
            key,
            text(record[key]),
          ]),
        ),
      ),
      groups,
    };
  }
  return { post };
});
