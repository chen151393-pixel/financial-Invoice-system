/**
 * @NApiVersion 2.1
 * @NModuleScope SameAccount
 */
/* global define */
define(["./customs_template", "./excel_template"], function (template, excel) {
  function render(data) {
    var company = data.company,
      customer = data.customer,
      declsreOrder = data.declsreOrder,
      country = data.country,
      port = data.port,
      packingType = data.packingType,
      packingNum = data.packingNum,
      grossWeight = data.grossWeight,
      netWeight = data.netWeight,
      transactionType = data.transactionType,
      lineData = data.lineData;
    var xml = excel.fill(template.header, [
      company,
      customer.replace(/[\u4e00-\u9fa5]/g, ""),
      company,
      declsreOrder,
      country,
      country,
      port,
      packingType,
      packingNum,
      grossWeight,
      netWeight,
      transactionType,
    ]);
    for (var i = 0; i < lineData.length; i++) {
      xml += excel.fill(template.row, [
        lineData[i].index,
        lineData[i].itemcustumNo,
        lineData[i].item,
        Number(lineData[i].quantity),
        lineData[i].unit,
        Number(lineData[i].unitAmount),
        Number(lineData[i].grossAmount),
        lineData[i].currency,
        country,
        lineData[i].goodPlace,
      ]);
    }
    return xml + excel.fill(template.footer, []);
  }
  return { render: render };
});
