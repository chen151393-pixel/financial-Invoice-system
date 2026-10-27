/**
 * @NApiVersion 2.1
 * @NModuleScope SameAccount
 */
/* global define */
define(["N/record"], function (record) {
  var sublistId = "recmachcustrecord_swc_relate_record";
  function read(id) {
    var source = record.load({ type: "customrecord_swc_declare_record", id: id, isDynamic: true });
    var count = source.getLineCount({ sublistId: sublistId });
    if (count <= 0) throw new Error("报关单没有发票打印明细");
    var option = {
      salesOrder: String(source.getValue({ fieldId: "custrecord_swc_declare_num" }) || "").split(
        "销售订单 #",
      )[1],
      created: source.getValue({ fieldId: "created" }),
      lineData: [],
      amountTotal: 0,
    };
    var _loop_1 = function (line) {
      var value = function (fieldId) {
        return source.getSublistValue({ sublistId: sublistId, fieldId: fieldId, line: line });
      };
      var item = {
        itemDesc: value("custrecord_swc_delare_name"),
        quantity: value("custrecord_swc_delare_quantity"),
        unitprice: Number(value("custrecord_swc_grossamountzj")).toFixed(2),
        grossAmount: Number(value("custrecord_swc_grossamount")).toFixed(2),
      };
      option.amountTotal += Number(item.grossAmount);
      option.lineData.push(item);
    };
    // 沿用原 PrintInvoice：申报单价和行金额分别读取，不用数量重新计算金额。
    // 原汇率查询结果未参与打印，提取后不再发起这次无效查询。
    for (var line = 0; line < count; line++) {
      _loop_1(line);
    }
    return option;
  }
  return { read: read };
});
