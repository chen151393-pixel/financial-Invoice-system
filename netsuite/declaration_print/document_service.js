/**
 * @NApiVersion 2.1
 * @NModuleScope SameAccount
 */
/* global define */
define(["./customs_reader", "./customs_excel", "./invoice_reader", "./invoice_excel"], function (
  customsReader,
  customsExcel,
  invoiceReader,
  invoiceExcel,
) {
  function build(id, type) {
    if (!/^[1-9][0-9]{0,19}$/.test(String(id))) throw new Error("报关单内部 ID 无效");
    if (type === "customs_declaration") {
      return {
        filename: "报关单打印.xls",
        format: "excel_xml",
        content: customsExcel.render(customsReader.read(String(id))),
      };
    }
    if (type === "invoice") {
      return {
        filename: "报关单发票打印.xls",
        format: "excel_xml",
        content: invoiceExcel.render(invoiceReader.read(String(id))),
      };
    }
    // 销售合同的打印来源尚未确认，不能返回空成功或用其他资料代替。
    throw new Error("该打印接口仅支持报关单和发票，销售合同尚未接入");
  }
  return { build: build };
});
