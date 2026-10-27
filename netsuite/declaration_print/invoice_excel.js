/**
 * @NApiVersion 2.1
 * @NModuleScope SameAccount
 */
/* global define */
define(["./invoice_template", "./excel_template"], function (template, excel) {
  function render(data) {
    var option = data;
    var time = option.created.toISOString();
    var xml = excel.fill(template.header, [option.title, option.salesOrder, time]);
    for (var i = 0; i < option.lineData.length; i++) {
      xml += excel.fill(template.row, [
        option.lineData[i].itemDesc,
        option.lineData[i].quantity,
        option.lineData[i].unitprice,
        option.lineData[i].grossAmount,
      ]);
    }
    return xml + excel.fill(template.footer, [option.amountTotal]);
  }
  return { render: render };
});
