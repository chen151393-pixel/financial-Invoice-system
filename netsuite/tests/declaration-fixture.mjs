// 合成报关数据：覆盖多行、金额独立于单价×数量、抬头优先和最后一行表头口径。
export function fixture({ special = false, empty = false } = {}) {
  const header = {
    custrecord_swc_declare_num: "销售订单 #SO-100",
    custrecord_swc_packingtype_sum: "纸箱",
    custrecord_swc_packingnum: 3,
    custrecord_swc_gross_weight: 40,
    custrecord_swc_netweight: 35,
    custrecord_swc_volume: 2,
    custrecord_swc_departure_port: "上海港",
    custrecord_swc_country_body: "美国",
    created: new Date("2026-10-01T02:00:00Z"),
  };
  const lines = empty
    ? []
    : [0, 1].map((index) => ({
        custrecord_swc_company: "采购公司",
        custrecord_swc_title: index ? "打印抬头" : "首行抬头",
        custrecord_swc_customer: "测试客户 Customer",
        custrecord_swc_country_list: "美国",
        custrecord_swc_transaction_type: "国外-FOB",
        custrecord_swc_delare_name: special ? '墨水 & <配件> "A"' : "墨水" + index,
        custrecord_swc_itemcode: String(10 + index),
        custrecord_swc_delare_quantity: index ? 3 : 2,
        custrecord_swc_delare_unit: "瓶",
        custrecord_swc_grossamountzj: index ? 4.5 : 12.34,
        custrecord_swc_grossamount: index ? 13.51 : 24.69,
        custrecord_swc_currency: "USD",
        custrecord_swc_last_country: "美国",
        custrecord_swc_goods_place: "上海",
      }));
  const calls = [];
  let selected = 0;
  const source = {
    getValue: ({ fieldId }) => header[fieldId],
    getText: ({ fieldId }) => header[fieldId],
    getLineCount: () => lines.length,
    selectLine: ({ line }) => {
      selected = line;
    },
    getCurrentSublistValue: ({ fieldId }) => lines[selected][fieldId],
    getCurrentSublistText: ({ fieldId }) => lines[selected][fieldId],
    getSublistValue: ({ fieldId, line }) => lines[line][fieldId],
  };
  return {
    calls,
    record: {
      load: (args) => {
        calls.push(args);
        return source;
      },
    },
    search: {
      lookupFields: ({ type }) =>
        type === "item" ? { custitem_custom_number: "321590" } : { custbody333341: [{ text: "香港客户" }] },
    },
    currency: { exchangeRate: () => 7 },
  };
}
