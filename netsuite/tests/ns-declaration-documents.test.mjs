import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fixture } from "./declaration-fixture.mjs";
import { loader } from "./declaration-loader.mjs";

const base = "netsuite/declaration_print/";
function setup(options) {
  const data = fixture(options);
  const load = loader({
    "N/record": data.record,
    "N/search": data.search,
    "N/encode": {
      Encoding: { UTF_8: "UTF_8", BASE_64: "BASE_64" },
      convert: ({ string }) => Buffer.from(string).toString("base64"),
    },
    "N/error": { create: ({ message }) => new Error(message) },
  });
  return { data, load, api: load("netsuite/declaration_documents_restlet.js") };
}

test("RESTlet 与已核实原打印函数在合成两行数据上输出一致，保留原金额", () => {
  const expected = JSON.parse(readFileSync(base + "original-output.sha256.json", "utf8"));
  const { api, data } = setup();
  for (const type of ["customs_declaration", "invoice"]) {
    const result = api.get({ id: "870", type });
    assert.equal(result.id, "870");
    assert.equal(result.type, type);
    assert.equal(result.files[0].format, "excel_xml");
    const xml = Buffer.from(result.files[0].contentBase64, "base64").toString();
    assert.equal(createHash("sha256").update(xml).digest("hex"), expected[type]);
    assert.match(xml, /24\.69/);
    assert.match(xml, /13\.51/);
  }
  assert.ok(data.calls.every((call) => call.type === "customrecord_swc_declare_record" && call.id === "870"));
});

test("特殊字符只作为单元格文本，不能注入 Excel XML", () => {
  const { api } = setup({ special: true });
  for (const type of ["customs_declaration", "invoice"]) {
    const xml = Buffer.from(api.get({ id: "870", type }).files[0].contentBase64, "base64").toString();
    assert.match(xml, /墨水 &amp; &lt;配件&gt; &quot;A&quot;/);
  }
});

test("非法 ID、未接入销售合同和空明细不返回成功文件", () => {
  const { api, data } = setup();
  for (const params of [
    { id: "../1", type: "invoice" },
    { id: "1", type: "sales_contract" },
    { id: "0", type: "invoice" },
  ]) {
    assert.throws(() => api.get(params));
  }
  assert.equal(data.calls.length, 0);
  assert.throws(() => setup({ empty: true }).api.get({ id: "1", type: "invoice" }), /没有/);
});
