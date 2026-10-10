import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import vm from "node:vm";

const code = await readFile(
  new URL("../finance_source_restlet.js", import.meta.url),
  "utf8",
);
const fields = [
  "id",
  "custrecord_swc_packing_main",
  "custrecord_swc_packinglist",
  "custrecord_swc_declare_company",
  "custrecord_swc_fulfillment_id",
  "custrecord_swc_fulfillment_line",
  "custrecord_swc_declare_item",
  "custrecord_details_item_name",
  "custrecord_swc_packingqty_2",
  "custrecord_swc_details_packingqty",
  "custrecord_swc_details_unit",
  "custrecord_swc_details_model",
  "custrecord_swc_detail_purchase",
];
function service(options = {}) {
  let result;
  const calls = [];
  const record = {
    load(input) {
      calls.push(input);
      if (options.fail) throw new Error("private NS error");
      return {
        getSublists: () => (options.noSublist ? [] : ["recmachcustrecord_swc_sl_relate"]),
        getSublistFields: () => (options.noFields ? [] : fields),
        getLineCount: () => options.count ?? 1,
        getValue: () => "CDTEST",
        getSublistValue: ({ fieldId }) =>
          fieldId === "id" ? "401" : fieldId === "custrecord_swc_packingqty_2" ? "1.2500" : "source",
      };
    },
  };
  vm.runInNewContext(code, {
    define: (_deps, factory) => {
      result = factory(record, {
        accountId: "123_SB1",
        getCurrentScript: () => ({ getRemainingUsage: () => options.usage ?? 1000 }),
      });
    },
  });
  return { api: result, calls };
}
test("只读原始子行保留身份、数量字符串及账套，未调用保存方法", () => {
  const { api, calls } = service();
  const result = api.post({ declarationIds: ["839"] });
  assert.equal(result.complete, true);
  assert.equal(result.account, "123-sb1");
  assert.equal(result.declarations[0].rows[0].sourceQuantity, "1.2500");
  assert.equal(result.declarations[0].rows[0].declarationQuantity, "source");
  assert.equal(result.declarations[0].rows[0].declarationUnitId, "source");
  assert.equal(result.declarations[0].rows[0].declarationModel, "source");
  assert.equal(result.declarations[0].rows[0].declarationId, "839");
  assert.equal(calls[0].type, "customrecord_swc_declare_record");
  assert.equal(calls.length, 1);
});
test("无效和越界请求在读取前拒绝", () => {
  for (const input of [
    null,
    {},
    { declarationIds: [] },
    { declarationIds: ["1", "1"] },
    { declarationIds: ["1"], recordType: "vendorBill" },
    { declarationIds: ["1 OR 1=1"] },
    { declarationIds: Array.from({ length: 21 }, (_, i) => String(i + 1)) },
  ]) {
    const { api, calls } = service();
    assert.equal(api.post(input).complete, false);
    assert.equal(calls.length, 0);
  }
});
test("子行不可见、身份重复、额度不足或读取失败均不冒充空成功", () => {
  for (const options of [
    { noSublist: true },
    { noFields: true },
    { count: 2001 },
    { count: 2 },
    { usage: 99 },
    { fail: true },
  ]) {
    const result = service(options).api.post({ declarationIds: ["839"] });
    assert.equal(result.complete, false);
    assert.equal(result.declarations, undefined);
    assert.doesNotMatch(JSON.stringify(result), /private NS error/);
  }
});
