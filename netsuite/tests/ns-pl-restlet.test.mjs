import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const keys = [
  "declaration",
  "date",
  "pl",
  "sales",
  "parent",
  "purchase",
  "origin",
  "vendor",
  "company",
  "name",
  "spec",
  "quantity",
  "unit",
  "price",
  "amount",
];
const tableKeys = [...keys, "customsPrice", "customsCurrency"];
function fixture() {
  return {
    complete: true,
    account: "TEST_SB1",
    requestId: "query-1",
    queryType: "pl",
    queryNumber: "PL001",
    queryMonth: "",
    queryCreatedFrom: "",
    queryCreatedTo: "",
    showIncomplete: true,
    readStartedAt: "2026-09-16T01:00:00Z",
    readCompletedAt: "2026-09-16T01:00:01Z",
    elapsedMs: 1000,
    monthDateLabel: "申报日期",
    counts: { customs: 2, purchase: 1, groups: 1, declarations: 0 },
    groups: [
      {
        key: "1",
        title: "CD000001",
        warnings: [],
        customsRows: [
          {
            values: {
              quantity: "60",
              amount: "119.99",
              price: "2.00",
              customsPrice: "1.98",
              customsCurrency: "人民币",
            },
          },
          {
            values: { quantity: "0", amount: "0", price: null, customsPrice: "0.00" },
            priceCalculated: true,
          },
        ],
        purchaseRows: [{ values: { quantity: "60", amount: "119.99", price: "2.00" } }],
        displayOrder: [
          { side: "customs", index: 0 },
          { side: "purchase", index: 0, note: "核对" },
          { side: "customs", index: 1 },
        ],
      },
    ],
  };
}
function setup(result, { exportedTableKeys = tableKeys } = {}) {
  const calls = [];
  const dependencies = {
    "./pl_query_service": {
      DISPLAY_KEYS: keys,
      TABLE_KEYS: exportedTableKeys,
      query(input, parameterPrefix) {
        assert.equal(parameterPrefix, "custscript_pw");
        calls.push(input);
        return result;
      },
    },
  };
  let bridge;
  vm.runInNewContext(readFileSync(new URL("../pl_restlet.js", import.meta.url), "utf8"), {
    define(names, factory) {
      assert.deepEqual(Array.from(names), ["./pl_query_service"], "JSON接口只依赖查询服务");
      bridge = factory(...names.map((name) => dependencies[name]));
    },
  });
  return { bridge, calls };
}
test("网站按NS顺序返回JSON且不二次计算金额，只查询一次", () => {
  const { bridge, calls } = setup(fixture());
  const result = JSON.parse(JSON.stringify(bridge.post({ pl: "PL001" })));
  assert.equal(calls.length, 1);
  assert.equal(result.contractVersion, 3);
  assert.ok(result.groups[0].rows.every((row) => row.cells.length === 17));
  assert.deepEqual(
    result.groups[0].rows.map((row) => row.side),
    ["customs", "purchase", "customs"],
  );
  assert.equal(result.groups[0].rows[1].cells[14], "119.99");
  assert.equal(result.groups[0].rows[1].cells[13], "2.00");
  assert.equal(result.groups[0].rows[2].cells[13], "—");
  assert.equal(result.groups[0].rows[2].cells[14], "0");
  assert.equal(result.groups[0].rows[0].cells[0], "未填写");
  assert.equal(result.groups[0].rows[0].cells[4], "未填写");
  assert.equal(result.groups[0].rows[1].cells[0], "", "采购行没有报关单号时保持空栏");
  assert.equal(result.groups[0].rows[0].cells[13], "2.00");
  assert.equal(result.groups[0].rows[0].cells[15], "1.98", "报关原单价不能被计算单价替代");
  assert.equal(result.groups[0].rows[0].cells[16], "人民币");
  assert.deepEqual(result.groups[0].rows[1].cells.slice(15), ["", ""], "采购行新增列留空");
  assert.deepEqual(result.groups[0].rows[2].cells.slice(15), ["0.00", ""], "原单价为零仍显示");
  assert.equal("download" in result, false);
  assert.equal("exportNotice" in result, false);
});
test("原单价直接保留NS格式化字符串，不转换大金额精度或补算空值", () => {
  const data = fixture();
  data.groups[0].customsRows[0].values.customsPrice = "9007199254740993123456789.01";
  data.groups[0].customsRows[1].values.customsPrice = null;
  const { bridge } = setup(data);
  const result = bridge.post({ pl: "PL001" });
  assert.equal(result.groups[0].rows[0].cells[15], "9007199254740993123456789.01");
  assert.equal(result.groups[0].rows[2].cells[15], "");
});

test("v3仅透传来源追溯的显式父行，不根据展示顺序猜配", () => {
  const data = fixture();
  data.queryType = "customsRecord";
  data.queryNumber = "CD000001";
  data.diagnostics = { total: 0 };
  const group = data.groups[0];
  group.title = "报关单 CD000001";
  group.customsRows.forEach((row, index) => {
    row.values.parentId = "101";
    row.rowKey = `source:${index}`;
  });
  group.purchaseRows[0].rowKey = "purchase:source:1";
  group.purchaseRows[0].values.currency = "CNY";
  // 显示在第一报关行后，明确引用却是第二行：必须尊重引用。
  group.displayOrder[1].customsIndex = 1;
  let actual = setup(data).bridge.post({ type: "customsRecord", pl: "CD000001" }).groups[0];
  assert.equal(actual.declarationId, "101");
  assert.equal(actual.recordNumber, "CD000001");
  assert.equal(actual.reviewIssues.length, 0);
  assert.equal(actual.rows[1].sourceKey, "purchase:source:1");
  assert.equal(actual.rows[1].customsRowId, "customs:1");
  assert.equal(actual.rows[1].currency, "CNY");
  delete group.displayOrder[1].customsIndex;
  actual = setup(data).bridge.post({ type: "customsRecord", pl: "CD000001" }).groups[0];
  assert.equal(actual.rows[1].customsRowId, null);
});
test("原字段缺失提示与NS页面一致，新增原单价缺失时保持空栏", () => {
  const data = fixture();
  data.groups[0].purchaseRows[0].values.price = null;
  data.groups[0].customsRows[0].values.customsPrice = null;
  const { bridge } = setup(data);
  const result = bridge.post({ pl: "PL001" });
  assert.equal(result.groups[0].rows[1].cells[13], "待确认");
  assert.equal(result.groups[0].rows[2].cells[13], "—");
  assert.equal(result.groups[0].rows[0].cells[15], "", "不得用仍存在的含税单价补齐原单价");
});
test("采购金额缺失时网站同NS页面保留关联行并留空，正常报关单价币种不受影响", () => {
  for (const priceCalculated of [false, true]) {
    const data = fixture();
    data.groups[0].purchaseRows[0] = {
      values: { quantity: "60", unit: "个", amount: null, price: null, purchase: "子采购001" },
      priceCalculated,
    };
    const { bridge, calls } = setup(data);
    const result = bridge.post({ pl: "PL001" });
    assert.equal(result.complete, true);
    assert.equal(result.contractVersion, 3);
    assert.equal(calls.length, 1);
    assert.equal(result.counts.purchase, 1);
    assert.equal(result.groups[0].rows[1].cells[5], "子采购001");
    assert.deepEqual(Array.from(result.groups[0].rows[1].cells.slice(11)), ["60", "个", "", "", "", ""]);
    assert.deepEqual(Array.from(result.groups[0].rows[0].cells.slice(15)), ["1.98", "人民币"]);
  }
});

test("旧服务缺少17列能力或列顺序不符时明确失败，不执行查询", () => {
  const swappedColumns = [...keys, "customsCurrency", "customsPrice"];
  const swappedLegacyColumns = [...tableKeys];
  [swappedLegacyColumns[0], swappedLegacyColumns[1]] = [swappedLegacyColumns[1], swappedLegacyColumns[0]];
  for (const exportedTableKeys of [null, keys, swappedColumns, swappedLegacyColumns]) {
    const { bridge, calls } = setup(fixture(), { exportedTableKeys });
    const result = bridge.post({ pl: "PL001" });
    assert.equal(result.complete, false);
    assert.equal(result.error.code, "SERVICE_VERSION_UNSUPPORTED");
    assert.equal(result.error.message, "NS共用查询服务版本不支持17列核对，请管理员更新共用查询脚本后重试。");
    assert.equal("groups" in result, false);
    assert.equal(calls.length, 0);
  }
});
test("NS失败原样返回，不重新查询", () => {
  const error = { complete: false, error: { code: "QUERY_FAILED", message: "本次查询失败" } };
  const { bridge, calls } = setup(error);
  assert.equal(bridge.post({ pl: "PL001" }), error);
  assert.equal(calls.length, 1);
});
test("NS入口拒绝客户端切换搜索、角色、脚本等额外参数", () => {
  const { bridge, calls } = setup(fixture());
  for (const input of [null, [], { pl: 123 }, { pl: "1", script: "other" }, { showIncomplete: "false" }]) {
    assert.equal(bridge.post(input).complete, false);
  }
  assert.equal(calls.length, 0);
});

test("共用服务为RESTlet读取独立参数，Suitelet仍保留原参数", () => {
  for (const prefix of ["custscript_pw", "custscript_pl"]) {
    const requested = [];
    let service;
    const root = new URL("../../SuiteScripts/pl_lookup/", import.meta.url);
    const config = readFileSync(new URL("pl_config.json", root), "utf8");
    const dependencies = {
      "N/runtime": {
        getCurrentUser: () => ({ id: 1 }),
        getCurrentScript: () => ({
          getRemainingUsage: () => 1000,
          getParameter: ({ name }) => {
            requested.push(name);
            return name.endsWith("config_file") ? "2530" : name.endsWith("purchase_search") ? "839" : "1047";
          },
        }),
      },
      "N/file": { load: () => ({ getContents: () => config }) },
      "N/log": { error: () => {} },
      "./pl_trace": { purchaseFields: {} },
    };
    vm.runInNewContext(readFileSync(new URL("pl_query_service.js", root), "utf8"), {
      define(names, factory) {
        service = factory(...names.map((name) => dependencies[name]));
      },
    });
    assert.deepEqual(Array.from(service.TABLE_KEYS), tableKeys, "测试契约与NS实际共用列定义一致");
    // 配置读取完成后故意缺少搜索适配，确保测试不执行任何NS调用。
    service.query({ pl: "PL001" }, prefix === "custscript_pl" ? undefined : prefix);
    // 当前direct配置仅需配置文件；两种入口均不再读取保存搜索参数。
    assert.deepEqual(requested, [prefix + "_config_file"]);
  }
});
