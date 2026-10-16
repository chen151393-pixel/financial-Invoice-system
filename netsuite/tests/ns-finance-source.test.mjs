import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import vm from "node:vm";

const code = await readFile(new URL("../finance_source_restlet.js", import.meta.url), "utf8");
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
      if (options.fail || options.failAt === calls.length) throw new Error("private NS error");
      const head = options.headers?.[input.id] ?? {};
      const sublists = head.sublists ?? {
        recmachcustrecord_swc_sl_relate: { fields: options.noFields ? [] : (head.fields ?? fields) },
      };
      const sublist = (sublistId) => {
        assert.ok(Object.hasOwn(sublists, sublistId), `未暴露的子列表：${sublistId}`);
        return sublists[sublistId];
      };
      return {
        getFields: () => {
          if (head.bodyFieldsFail) throw new Error("private NS error");
          return ["name", "custrecord_swc_realno"];
        },
        getSublists: () => {
          if (head.sublistsFail) throw new Error("private NS error");
          return options.noSublist ? [] : Object.keys(sublists);
        },
        getSublistFields: ({ sublistId }) => {
          const current = sublist(sublistId);
          if (current.fieldsFail) throw new Error("private NS error");
          return current.fields;
        },
        getLineCount: ({ sublistId }) => {
          const current = sublist(sublistId);
          if (current.countFail) throw new Error("private NS error");
          return current.count ?? head.count ?? options.count ?? 1;
        },
        getValue: () => {
          assert.ok(!options.metadataOnly, "诊断不得读取业务字段值");
          return head.number ?? "CDTEST";
        },
        getSublistValue: ({ sublistId, fieldId, line }) => {
          assert.ok(!options.metadataOnly, "诊断不得读取业务行");
          sublist(sublistId);
          if (fieldId === "id" || fieldId === "internalid") return head.ids?.[line] ?? "401";
          if (head.values && Object.hasOwn(head.values, fieldId)) return head.values[fieldId];
          return fieldId === "custrecord_swc_packingqty_2" ? "1.2500" : "source";
        },
      };
    },
  };
  vm.runInNewContext(code, {
    define: (_deps, factory) => {
      result = factory(record, {
        accountId: "123_SB1",
        getCurrentScript: () => ({
          getRemainingUsage: () => options.usage ?? 1000,
          getParameter: ({ name }) => {
            assert.equal(name, "custscript_fin_source_sublist");
            return options.configuredSublist ?? null;
          },
        }),
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
    { declarationIds: ["839"], action: "save" },
    { declarationIds: ["839"], action: null },
    { declarationIds: ["839"], action: "diagnose", sublistId: "item" },
  ]) {
    const { api, calls } = service();
    assert.equal(api.post(input).complete, false);
    assert.equal(calls.length, 0);
  }
});

test("批量诊断返回各单实际结构，不读取行数据也不被当成来源成功", () => {
  const { api, calls } = service({
    metadataOnly: true,
    headers: {
      839: {
        sublists: {
          recmachcustrecord_actual: { fields, count: 2 },
          mediaitem: { fields: ["file"], count: 0 },
        },
      },
      840: { sublists: {} },
    },
  });
  const result = api.post({ declarationIds: ["839", "840"], action: "diagnose" });
  assert.equal(result.mode, "diagnose");
  assert.equal(result.complete, false);
  assert.equal(result.diagnosticsComplete, true);
  assert.equal(result.declarations, undefined);
  assert.equal(calls.length, 2);
  const [first, second] = result.diagnostics;
  assert.equal(first.expectedSublistVisible, false);
  assert.equal(first.bodyFields[0], "name");
  assert.equal(first.sublists[0].sublistId, "recmachcustrecord_actual");
  assert.equal(first.sublists[0].fields.length, fields.length);
  assert.equal(first.sublists[0].lineCount, 2);
  assert.equal(first.sublists[0].identityField, "id");
  assert.equal(first.sublists[0].missingFields.length, 0);
  assert.equal(first.sublists[1].lineCount, 0);
  assert.equal(first.sublists[1].identityField, "");
  assert.equal(second.id, "840");
  assert.equal(second.sublists.length, 0);
});

test("读取失败附带可见结构，不自动选用字段相同的其他子列表", () => {
  const result = service({
    headers: {
      839: { sublists: { recmachcustrecord_actual: { fields, count: 1 } } },
    },
  }).api.post({ declarationIds: ["839"] });
  assert.equal(result.error.code, "RAW_SUBLIST_UNAVAILABLE");
  assert.equal(result.error.diagnostic.sublists[0].sublistId, "recmachcustrecord_actual");
  assert.equal(result.declarations, undefined);
  const missing = service({
    headers: { 839: { fields: fields.filter((field) => field !== "id") } },
  }).api.post({ declarationIds: ["839"] });
  assert.equal(missing.error.code, "RAW_FIELDS_UNAVAILABLE");
  assert.equal(missing.error.identityFieldMissing, true);
  assert.equal(missing.error.diagnostic.expectedSublistVisible, true);
});

test("部署配置可切换核实后的子列表，仍校验来源完整性", () => {
  const options = {
    configuredSublist: "recmachcustrecord_actual",
    headers: {
      839: { sublists: { recmachcustrecord_actual: { fields, count: 1 } } },
    },
  };
  const result = service(options).api.post({ declarationIds: ["839"], action: "read" });
  assert.equal(result.complete, true);
  assert.equal(result.declarations[0].rows[0].id, "401");
  options.headers[839].sublists.recmachcustrecord_actual.fields = ["id"];
  assert.equal(service(options).api.post({ declarationIds: ["839"] }).error.code, "RAW_FIELDS_UNAVAILABLE");
  const invalid = service({ configuredSublist: "item" });
  assert.equal(invalid.api.post({ declarationIds: ["839"] }).error.code, "INVALID_SOURCE_CONFIG");
  assert.equal(invalid.calls.length, 0);
});

test("单张加载失败或结构读取失败不会阻断其他单据诊断，也不泄露原始异常", () => {
  const { api } = service({
    metadataOnly: true,
    failAt: 1,
    headers: {
      840: {
        sublists: {
          recmachcustrecord_actual: { fieldsFail: true, count: 0 },
          other: { fields, countFail: true },
        },
      },
      841: { bodyFieldsFail: true, sublistsFail: true },
    },
  });
  const result = api.post({ declarationIds: ["839", "840", "841", "842"], action: "diagnose" });
  assert.equal(result.diagnosticsComplete, false);
  assert.equal(result.diagnostics[0].issues[0], "HEADER_LOAD_FAILED");
  assert.equal(result.diagnostics[1].sublists[0].issues[0], "FIELDS_READ_FAILED");
  assert.equal(result.diagnostics[1].sublists[0].lineCount, 0);
  assert.equal(result.diagnostics[1].sublists[1].lineCount, null);
  assert.equal(result.diagnostics[1].sublists[1].issues[0], "LINE_COUNT_READ_FAILED");
  assert.equal(result.diagnostics[2].issues.length, 2);
  assert.equal(result.diagnostics[3].inspectionComplete, true);
  assert.doesNotMatch(JSON.stringify(result), /private NS error/);
  const limited = service({ usage: 99 });
  assert.equal(
    limited.api.post({ declarationIds: ["839"], action: "diagnose" }).diagnostics[0].issues[0],
    "QUERY_LIMIT",
  );
  assert.equal(limited.calls.length, 0);
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

test("不同报关单批量读取保留各自归属，兼容 internalid 身份字段", () => {
  const { api } = service({
    headers: {
      839: { number: "CD000839", ids: ["401"] },
      840: { number: "CD000840", ids: ["402"], fields: fields.map((f) => (f === "id" ? "internalid" : f)) },
    },
  });
  const result = api.post({ declarationIds: ["839", "840"] });
  assert.equal(result.complete, true);
  assert.equal(result.contractVersion, 1);
  assert.equal(result.declarations[1].recordNumber, "CD000840");
  assert.equal(result.declarations[1].rows[0].id, "402");
  assert.equal(result.declarations[1].rows[0].declarationId, "840");
});

test("跨单据重复、后续读取失败和累计超限都不泄露部分成功", () => {
  for (const options of [
    {},
    { failAt: 2 },
    {
      headers: {
        839: { count: 1001, ids: Array.from({ length: 1001 }, (_, i) => String(i + 1)) },
        840: { count: 1000 },
      },
    },
  ]) {
    const { api } = service(options);
    const result = api.post({ declarationIds: ["839", "840"] });
    assert.equal(result.complete, false);
    assert.equal(result.declarations, undefined);
    assert.equal(result.contractVersion, 1);
    assert.equal(result.account, "123-sb1");
  }
});

test("可见的空子列表返回空数组，零数量与空引用保持来源含义", () => {
  const empty = service({ count: 0 }).api.post({ declarationIds: ["839"] });
  assert.equal(empty.complete, true);
  assert.equal(empty.declarations[0].rows.length, 0);
  const { api } = service({
    headers: {
      839: {
        values: {
          custrecord_swc_packingqty_2: 0,
          custrecord_swc_packinglist: null,
        },
      },
    },
  });
  const row = api.post({ declarationIds: ["839"] }).declarations[0].rows[0];
  assert.equal(row.sourceQuantity, "0");
  assert.equal(row.packingId, "");
});

test("拒绝数字输入、超长行身份及不可见的报关编号", () => {
  const { api, calls } = service();
  assert.equal(api.post({ declarationIds: [839] }).error.code, "INVALID_INPUT");
  assert.equal(calls.length, 0);
  assert.equal(
    service({ headers: { 839: { ids: ["1".repeat(21)] } } }).api.post({ declarationIds: ["839"] }).error.code,
    "INVALID_SOURCE_ID",
  );
  assert.equal(
    service({ headers: { 839: { number: "" } } }).api.post({ declarationIds: ["839"] }).error.code,
    "HEADER_FIELDS_UNAVAILABLE",
  );
});
