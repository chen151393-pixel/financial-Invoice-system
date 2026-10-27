/**
 * @NApiVersion 2.1
 * @NModuleScope SameAccount
 */
/* global define */
define([], function () {
  // 原模板只插入单元格值；转义数据，防止品名中的 &、< 破坏 XML 或注入公式。
  function fill(template, values) {
    return template.replace(/\{\{(\d+)\}\}/g, function (_, index) {
      var text = String(values[Number(index)]);
      for (var offset = 0; offset < text.length; offset++) {
        var code = text.charCodeAt(offset);
        if (code < 32 && [9, 10, 13].indexOf(code) === -1) {
          throw new Error("打印字段包含无效控制字符，请先核对 NS 数据");
        }
      }
      return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&apos;");
    });
  }
  return { fill: fill };
});
