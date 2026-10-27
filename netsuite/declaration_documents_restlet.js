/**
 * @NApiVersion 2.1
 * @NScriptType Restlet
 * @NModuleScope SameAccount
 */
/* global define */
define(["N/encode", "N/error", "./declaration_print/document_service"], (encode, error, documents) => {
  function get(params) {
    const id = String(params.id || "");
    const type = params.type;
    if (!/^[1-9][0-9]{0,19}$/.test(id) || !["customs_declaration", "invoice"].includes(type)) {
      throw error.create({
        name: "INVALID_DOCUMENT_REQUEST",
        message: "仅支持有效报关单 ID 及 customs_declaration / invoice；销售合同尚未接入",
        notifyOff: true,
      });
    }
    const result = documents.build(id, type);
    const contentBase64 = encode.convert({
      string: result.content,
      inputEncoding: encode.Encoding.UTF_8,
      outputEncoding: encode.Encoding.BASE_64,
    });
    if (contentBase64.length > Math.ceil((7 * 1024 * 1024) / 3) * 4) {
      throw error.create({
        name: "DOCUMENT_TOO_LARGE",
        message: "打印文件超过 7 MB，未返回截断内容",
        notifyOff: true,
      });
    }
    return { id, type, files: [{ filename: result.filename, format: result.format, contentBase64 }] };
  }
  return { get };
});
