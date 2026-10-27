/**
 * @NApiVersion 2.1
 * @NModuleScope SameAccount
 */
/* global define */
define(["N/record", "N/search"], function (record, search) {
  var sublistId = "recmachcustrecord_swc_relate_record";
  // 来自正式环境 PrintDeclaration；保留原表头取最后一行及原打印金额口径。
  function read(id) {
    var source = record.load({ type: "customrecord_swc_declare_record", id: id, isDynamic: true });
    var value = function (fieldId) {
      return source.getValue({ fieldId: fieldId });
    };
    var text = function (fieldId) {
      return source.getText({ fieldId: fieldId });
    };
    var lineValue = function (fieldId) {
      return source.getCurrentSublistValue({ sublistId: sublistId, fieldId: fieldId });
    };
    var lineText = function (fieldId) {
      return source.getCurrentSublistText({ sublistId: sublistId, fieldId: fieldId });
    };
    var count = source.getLineCount({ sublistId: sublistId });
    if (count <= 0) throw new Error("报关单没有打印明细");
    var data = {
      declsreOrder: String(value("custrecord_swc_declare_num") || "").split("销售订单 #")[1] || "",
      packingType: text("custrecord_swc_packingtype_sum"),
      packingNum: value("custrecord_swc_packingnum"),
      grossWeight: value("custrecord_swc_gross_weight"),
      netWeight: value("custrecord_swc_netweight"),
      port: value("custrecord_swc_departure_port"),
      lineData: [],
    };
    var countryBody = value("custrecord_swc_country_body");
    for (var line = 0; line < count; line++) {
      source.selectLine({ sublistId: sublistId, line: line });
      data.company = lineText("custrecord_swc_title") || lineText("custrecord_swc_company") || "";
      data.customer = lineText("custrecord_swc_customer") || "";
      if (lineText("custrecord_swc_country_list") == "95") {
        var salesId = lineValue("custrecord_swc_salesorder_number") || "";
        var customer = search.lookupFields({ type: "salesorder", id: salesId, columns: "custbody333341" })
          .custbody333341[0];
        data.customer = customer ? customer.text : "";
      }
      data.country = countryBody == "95" ? "中国香港" : text("custrecord_swc_country_body") || "";
      data.transactionType = (lineValue("custrecord_swc_transaction_type") || "").replace("国外-", "");
      var item = lineValue("custrecord_swc_itemcode") || "";
      data.lineData.push({
        index: line + 1,
        item: lineValue("custrecord_swc_delare_name") || "",
        itemcustumNo:
          search.lookupFields({ type: "item", id: item, columns: "custitem_custom_number" })
            .custitem_custom_number || "",
        quantity: lineValue("custrecord_swc_delare_quantity") || "",
        unit: lineText("custrecord_swc_delare_unit") || "",
        unitAmount: Number(lineValue("custrecord_swc_grossamountzj")).toFixed(2) || "0.00",
        grossAmount: Number(lineValue("custrecord_swc_grossamount")).toFixed(2),
        currency: lineText("custrecord_swc_currency") || "",
        country: lineText("custrecord_swc_last_country") || "",
        goodPlace: lineText("custrecord_swc_goods_place") || "",
      });
    }
    return data;
  }
  return { read: read };
});
