import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const root = new URL("../../SuiteScripts/pl_lookup/", import.meta.url);
const clone = (value) => JSON.parse(JSON.stringify(value));
function load(name, dependencies = {}) {
  let exported;
  vm.runInNewContext(readFileSync(new URL(name, root), "utf8"), {
    define: (names, factory) => {
      exported = factory(...names.map((key) => dependencies[key]));
    },
  });
  return exported;
}
const child = "custrecord_swc_subpo_main";
const header = "custrecord_swc_relate_record";
function fixtures() {
  return {
    customrecord_swc_packing: [{ internalid: "70", name: "PL001" }],
    customrecord_swc_declare_record: [
      {
        internalid: "74",
        name: "CD000074",
        custrecord_swc_realno: "BG001",
        custrecord315: "2026-09-15",
        created: "2026-09-15",
      },
    ],
    customrecord_swc_declare_line: [
      {
        internalid: "1",
        custrecord_swc_sl_relate: "74",
        "custrecord_swc_sl_relate.name": "CD000074",
        custrecord_swc_packing_main: "70",
        custrecord_swc_packinglist: "1",
        custrecord_swc_declare_company: "3",
        custrecord_swc_fulfillment_id: "100",
        custrecord_swc_fulfillment_line: "1",
        custrecord_swc_declare_item: "900",
        custrecord_details_item_name: "胸章机",
        custrecord_swc_packingqty_2: "10",
      },
    ],
    customrecord_swc_packinglist: [
      {
        internalid: "1",
        custrecord_swc_sublist_packingmain: "70",
        custrecord_swc_sublist_fulreq_tranid: "100",
        custrecord_swc_sublist_fulreq_lineid: "1",
        custrecord_swc_sublist_itemid: "900",
        custrecord_swc_sublist_createdfrom: "SO1",
        custrecord_swc_so_lineid: "7",
        custrecord_swc_sublist_purchaseorderhead: "3",
        custrecord_swc_sublist_purchasesource: "city1",
        custrecord_swc_sublist_actualpackingqty: "10",
        custrecord_swc_sublist_purchasetax: "1",
      },
    ],
    customrecord_swc_delare_detail: [
      {
        internalid: "622",
        custrecord_swc_relate_record: "74",
        custrecord_swc_packing_no: "70",
        custrecord_swc_company: "3",
        [`${header}.custrecord_swc_realno`]: "BG001",
        custrecord_swc_salesorder_number: "SO原值",
        custrecord_swc_goods_place: "city1",
        custrecord_swc_delare_name: "胸章机",
        custrecord_swc_huge: "58mm",
        custrecord_swc_quantity: "1272",
        custrecord_swc_unit: "卷",
        custrecord_swc_delare_quantity: "5",
        custrecord_swc_delare_unit: "套",
        custrecord_swc_grossamount: "132.74",
        custrecord_swc_unitprice: "0.64",
        custrecord_swc_currency: "US Dollar",
      },
    ],
    customrecord_swc_subpo_item: [
      {
        internalid: "9601",
        custrecord_swc_subpo_main: "548",
        [`${child}.internalid`]: "548",
        [`${child}.name`]: "子采购001",
        [`${child}.custrecord_swc_subpo_plnum`]: "70",
        [`${child}.custrecord_swc_subpo_class`]: "3",
        [`${child}.custrecord_swc_subpo_vendor`]: "供应商甲",
        [`${child}.custrecord_swc_subpo_baoguannum`]: "74",
        [`${child}.custrecord_swc_subpo_istax`]: "T",
        [`${child}.custrecord_swc_subpo_so`]: "SO1",
        custrecord_swc_subpo_item_solineid: "7",
        custrecord_swc_subpo_item_ifreqid: "100",
        custrecord_swc_subpo_item_item: "900",
        custrecord_swc_subpo_item_bgname: "胸章机",
        custrecord_swc_subpo_item_qty: "10",
        custrecord_swc_subpo_item_bgqty: "10",
        custrecord_swc_subpo_item_bgunit: "台",
        custrecord_swc_subpo_item_amountwithtax: "913.00",
      },
    ],
  };
}
function harness({
  changeConfig,
  changeData,
  failType,
  changeSecondRead,
  changePaged,
  searchFault,
  legacy = false,
} = {}) {
  const config = JSON.parse(readFileSync(new URL("pl_config.json", root), "utf8"));
  if (legacy) {
    config.queryMode = "savedSearch";
    config.purchase.resultMode = "summary";
    for (const [key, value] of Object.entries(config.purchase.columns))
      value.summary = key === "parent" ? "MAX" : ["amount", "quantity"].includes(key) ? "SUM" : "GROUP";
  }
  changeConfig?.(config);
  const data = fixtures();
  changeData?.(data);
  const calls = { loads: 0, parameters: [], searches: [], logs: [] };
  let purchaseReads = 0;
  function matches(row, expression) {
    if (!expression || (Array.isArray(expression) && !expression.length)) return true;
    if (Array.isArray(expression[0]) || typeof expression[0] === "object") {
      return expression.filter((x) => typeof x !== "string").every((x) => matches(row, x));
    }
    const [name, operator, input] = Array.isArray(expression)
      ? expression
      : [
          expression.join ? `${expression.join}.${expression.name}` : expression.name,
          expression.operator,
          expression.values,
        ];
    const value = row[name] ?? (name.endsWith("isinactive") ? "F" : null);
    const values = Array.isArray(input) ? input : [input];
    if (["anyof", "is", "equalto"].includes(operator)) return values.includes(value);
    if (operator === "onorafter") return value != null && value >= input;
    if (operator === "before") return value != null && value < input;
    throw new Error(`未实现测试筛选操作：${operator}`);
  }
  const result = (row, recordType) => ({
    getValue: (column) => {
      searchFault?.({ operation: "getValue", recordType, column });
      return row[column.join ? `${column.join}.${column.name}` : column.name] ?? null;
    },
    getText: (column) => {
      searchFault?.({ operation: "getText", recordType, column });
      return row[column.join ? `${column.join}.${column.name}` : column.name] ?? null;
    },
  });
  const search = {
    Operator: { IS: "is", ANYOF: "anyof", EQUALTO: "equalto", ONORAFTER: "onorafter", BEFORE: "before" },
    Sort: { ASC: "ASC" },
    createColumn: (column) => {
      searchFault?.({ operation: "createColumn", column });
      return { ...column };
    },
    createFilter: (filter) => ({ ...filter }),
    load: ({ id }) => {
      calls.loads++;
      if (legacy) {
        const spec = id === "839" ? config.purchase : config.customs;
        const columns = Object.values(spec.columns).filter(
          (column, index, list) =>
            list.findIndex(
              (other) =>
                other.name === column.name && other.join === column.join && other.summary === column.summary,
            ) === index,
        );
        return search.create({ type: spec.recordType, columns });
      }
      throw new Error("direct不允许加载保存搜索");
    },
    create: (options) => {
      searchFault?.({ operation: "create", recordType: options.type });
      const created = {
        searchType: options.type,
        columns: options.columns,
        filterExpression: options.filters,
        run: () => ({
          getRange: () =>
            (data[options.type] || [])
              .filter((r) => matches(r, created.filterExpression))
              .map((row) => result(row, options.type)),
        }),
        runPaged: ({ pageSize }) => {
          searchFault?.({ operation: "runPaged", recordType: options.type });
          if (options.type === failType) throw new Error("字段或权限不允许查询");
          if (options.type === "customrecord_swc_subpo_item" && ++purchaseReads === 2)
            changeSecondRead?.(data);
          const rows = (data[options.type] || []).filter((r) => matches(r, created.filterExpression));
          const paged = {
            count: rows.length,
            pageRanges: Array.from({ length: Math.ceil(rows.length / pageSize) }, (_, index) => ({ index })),
            fetch: ({ index }) => {
              searchFault?.({ operation: "fetch", recordType: options.type });
              return {
                data: rows
                  .slice(index * pageSize, (index + 1) * pageSize)
                  .map((row) => result(row, options.type)),
              };
            },
          };
          changePaged?.(paged, options.type, purchaseReads);
          return paged;
        },
      };
      calls.searches.push(created);
      return created;
    },
  };
  const decimal = load("pl_decimal.js");
  const service = load("pl_query_service.js", {
    "N/search": search,
    "./pl_decimal": decimal,
    "./pl_trace": load("pl_trace.js", { "N/search": search, "./pl_decimal": decimal }),
    "N/runtime": {
      accountId: "TEST",
      getCurrentUser: () => ({ id: 1, role: 1001 }),
      getCurrentScript: () => ({
        getRemainingUsage: () => 1000,
        getParameter: ({ name }) => {
          calls.parameters.push(name);
          return name.endsWith("config_file")
            ? "2530"
            : legacy
              ? name.endsWith("purchase_search")
                ? "839"
                : "954"
              : "故意无效的旧搜索参数";
        },
      }),
    },
    "N/file": { load: () => ({ getContents: () => JSON.stringify(config) }) },
    "N/format": {
      Type: { DATE: "date" },
      format: ({ value }) =>
        `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`,
    },
    "N/log": { audit: (entry) => calls.logs.push(entry), error: (entry) => calls.logs.push(entry) },
  });
  return { calls, service, query: (input = { pl: "PL001" }) => clone(service.query(input)) };
}

test("PL、CD及真实报关号查询：Packing历史销售行号失效仍关联两张母采购的子采购，并同步导出", () => {
  for (const input of [
    { pl: "PL001" },
    { type: "customsRecord", pl: "CD000074" },
    { type: "declaration", pl: "BG001" },
  ]) {
    const h = harness({
      changeData(data) {
        const raw = data.customrecord_swc_declare_line[0];
        const pack = data.customrecord_swc_packinglist[0];
        const purchase = data.customrecord_swc_subpo_item[0];
        // 已读正式数据的两条代表来源：黑色帽及荧光粉色帽；其余内容为隔离样本。
        const cases = [
          ["2881", "228740", "105245", "9", "12", "551", "YE-KRQ251231-Y592-1", "4400", "15972"],
          ["2882", "228741", "110091", "10", "13", "552", "YE-KRQ251231-Y592-1-1", "400", "1452"],
        ];
        data.customrecord_swc_declare_line = cases.map(([id, mother, item, , , , , qty]) => ({
          ...raw,
          internalid: id,
          custrecord_swc_packinglist: id,
          custrecord_swc_declare_item: item,
          custrecord_swc_detail_purchase: mother,
          custrecord_swc_packingqty_2: qty,
        }));
        data.customrecord_swc_packinglist = cases.map(([id, mother, item, oldLine, , , , qty]) => ({
          ...pack,
          internalid: id,
          custrecord_swc_sublist_protranid: mother,
          custrecord_swc_sublist_itemid: item,
          custrecord_swc_so_lineid: oldLine,
          custrecord_swc_sublist_actualpackingqty: qty,
        }));
        data.customrecord_swc_subpo_item = cases.map(
          ([id, mother, item, , salesLine, sub, name, qty, amount]) => ({
            ...purchase,
            internalid: id,
            custrecord_swc_subpo_main: sub,
            [`${child}.internalid`]: sub,
            [`${child}.name`]: name,
            [`${child}.custrecord_swc_subpo_mainpo`]: mother,
            custrecord_swc_subpo_item_item: item,
            custrecord_swc_subpo_item_mainpo_lineid: "1",
            custrecord_swc_subpo_item_solineid: salesLine,
            custrecord_swc_subpo_item_qty: qty,
            custrecord_swc_subpo_item_bgqty: qty,
            custrecord_swc_subpo_item_amountwithtax: amount,
          }),
        );
        data.salesorder = cases.map(([, mother, item, , salesLine]) => ({
          internalid: "SO1",
          line: salesLine,
          item,
          applyingtransaction: mother,
          "applyingTransaction.line": "1",
          "applyingtransaction.type": "PurchOrd",
          mainline: "F",
          taxline: "F",
        }));
      },
    });
    const result = h.query(input);
    assert.equal(result.complete, true, JSON.stringify(h.calls.logs));
    assert.deepEqual(
      result.groups[0].displayOrder.map((r) => r.side),
      ["customs", "purchase", "purchase"],
    );
    assert.deepEqual(
      result.groups[0].purchaseRows.map((r) => [r.values.purchase, r.values.quantity, r.values.amount]),
      [
        ["YE-KRQ251231-Y592-1", "4400", "15972"],
        ["YE-KRQ251231-Y592-1-1", "400", "1452"],
      ],
    );
    const xml = load("pl_excel.js", { "./pl_query_service": h.service }).buildParts(result)[
      "xl/worksheets/sheet1.xml"
    ];
    assert.match(xml, /YE-KRQ251231-Y592-1-1/);
    assert.match(xml, /<v>15972<\/v>/);
  }
});

test("direct使用实际配置的物理字段直接读取，PL及CD查询保持来源关联和两侧单位金额", () => {
  for (const input of [{ pl: "PL001" }, { type: "customsRecord", pl: "CD000074" }]) {
    const h = harness();
    const r = h.query(input);
    assert.equal(r.complete, true, JSON.stringify(h.calls.logs));
    assert.equal(r.counts.purchase, 1);
    assert.equal(r.counts.customs, 1);
    const p = r.groups[0].purchaseRows[0].values;
    assert.equal(p.quantity, "10");
    assert.equal(p.amount, "913");
    assert.equal(p.unit, "台");
    assert.equal(p.price, "91.30");
    const c = r.groups[0].customsRows[0].values;
    assert.equal(c.quantity, "5");
    assert.equal(c.amount, "132.74");
    assert.equal(c.unit, "套");
    assert.equal(c.price, "26.55");
    assert.equal(c.customsPrice, "0.64");
    assert.equal(c.customsCurrency, "US Dollar");
    assert.equal(p.customsPrice, null);
    assert.equal(p.customsCurrency, null);
    assert.equal(h.service.DISPLAY_KEYS.length, 15);
    assert.equal(h.service.TABLE_KEYS.length, 17);
    assert.equal(c.sales, "SO原值");
    assert.equal(h.calls.loads, 0);
    assert.deepEqual(h.calls.parameters, ["custscript_pl_config_file"]);
    const created = h.calls.searches.find((s) => s.searchType === "customrecord_swc_subpo_item");
    const signatures = created.columns.map((c) => `${c.join || ""}.${c.name}`);
    assert.equal(new Set(signatures).size, signatures.length);
    assert.equal(created.columns[0].name, "internalid");
    assert.equal(created.columns[0].sort, "ASC");
    const excel = load("pl_excel.js", { "./pl_query_service": h.service }).buildParts(r)[
      "xl/worksheets/sheet1.xml"
    ];
    assert.match(excel, /<v>913<\/v>/);
    assert.match(excel, /91\.30/);
    const customsExcelRow = excel.match(/<row r="2"[^>]*>.*?<\/row>/)[0];
    assert.match(customsExcelRow, /<c r="L2"[^>]*><v>5<\/v>/);
    assert.match(customsExcelRow, /<c r="M2"[^>]*>.*?<t[^>]*>套<\/t>/);
    assert.match(customsExcelRow, /<c r="N2"[^>]*><v>26\.55<\/v>/);
    assert.doesNotMatch(customsExcelRow, /1272|卷/);
    assert.match(customsExcelRow, /<c r="P2"[^>]*><v>0\.64<\/v>/);
    assert.match(customsExcelRow, /<c r="Q2"[^>]*>.*?<t[^>]*>US Dollar<\/t>/);
    const purchaseExcelRow = excel.match(/<row r="3"[^>]*>.*?<\/row>/)[0];
    for (const column of ["P", "Q"])
      assert.match(purchaseExcelRow, new RegExp(`<c r="${column}3"[^>]*><is><t[^>]*><\\/t><\\/is><\\/c>`));
  }
});

test("报关原单价及币种允许缺失，零单价保留且非法价格明确失败", () => {
  for (const [value, expected] of [
    [null, null],
    ["0", "0.00"],
    ["0.645", "0.65"],
  ]) {
    const h = harness({
      changeData: (data) => {
        data.customrecord_swc_delare_detail[0].custrecord_swc_unitprice = value;
        data.customrecord_swc_delare_detail[0].custrecord_swc_currency = null;
      },
    });
    const result = h.query();
    assert.equal(result.complete, true, JSON.stringify(result.error));
    const values = result.groups[0].customsRows[0].values;
    assert.equal(values.customsPrice, expected);
    assert.equal(values.customsCurrency, null);
    assert.equal(values.price, "26.55");
    assert.equal(values.amount, "132.74");
  }
  const failed = harness({
    changeData: (data) => {
      data.customrecord_swc_delare_detail[0].custrecord_swc_unitprice = "invalid-price";
    },
  }).query();
  assert.equal(failed.complete, false);
  assert.equal(failed.error.diagnostic.fieldName, "custrecord_swc_unitprice");
  assert.equal(failed.error.diagnostic.stage, "CUSTOMS_SEARCH");
});

test("本次报关数量为空或零时不回退原数量，采购数量、单位和金额保持", () => {
  for (const quantity of [null, "0"]) {
    const h = harness({
      changeData: (data) => {
        data.customrecord_swc_delare_detail[0].custrecord_swc_delare_quantity = quantity;
        data.customrecord_swc_delare_detail[0].custrecord_swc_delare_unit = null;
      },
    });
    const result = h.query();
    assert.equal(result.complete, true, JSON.stringify(result.error));
    const customs = result.groups[0].customsRows[0].values;
    assert.equal(customs.quantity, quantity);
    assert.equal(customs.unit, null);
    assert.equal(customs.price, null);
    assert.equal(customs.amount, "132.74");
    const purchase = result.groups[0].purchaseRows[0].values;
    assert.equal(purchase.quantity, "10");
    assert.equal(purchase.unit, "台");
    assert.equal(purchase.amount, "913");
    assert.equal(purchase.price, "91.30");
  }
});

test("direct排除停用明细、停用父记录及范围外记录，重复内部ID不重复计价", () => {
  const h = harness({
    changeData: (data) => {
      for (const [type, scopeField] of [
        ["customrecord_swc_subpo_item", `${child}.custrecord_swc_subpo_plnum`],
        ["customrecord_swc_delare_detail", header],
      ]) {
        const row = data[type][0];
        const parent = type === "customrecord_swc_subpo_item" ? child : header;
        data[type].push(
          { ...row },
          { ...row, internalid: "90001", isinactive: "T" },
          { ...row, internalid: "90002", [`${parent}.isinactive`]: "T" },
          { ...row, internalid: "90003", [scopeField]: "999" },
        );
      }
    },
  });
  const r = h.query();
  assert.equal(r.complete, true, JSON.stringify(h.calls.logs));
  assert.equal(r.counts.purchase, 1);
  assert.equal(r.counts.customs, 1);
  assert.equal(r.groups[0].purchaseRows[0].values.amount, "913");
  assert.equal(r.counts.deduplicated, 2);
});

test("direct空条件拒绝、未知单号不创建无范围业务查询", () => {
  for (const input of [{}, { pl: "PL不存在" }, { type: "customsRecord", pl: "CD999999" }]) {
    const h = harness();
    const r = h.query(input);
    assert.equal(h.calls.loads, 0);
    assert.equal(
      h.calls.searches.some((s) =>
        ["customrecord_swc_subpo_item", "customrecord_swc_delare_detail"].includes(s.searchType),
      ),
      false,
    );
    if (input.pl) assert.equal(r.complete, true, JSON.stringify({ input, r, logs: h.calls.logs }));
    else assert.equal(r.complete, false);
  }
});

test("PL没有原始报关来源时，控制台诊断区分汇总明细存在和子采购有头无行，展示范围不变", () => {
  const h = harness({
    changeData(data) {
      data.customrecord_swc_declare_line = [];
      data.customrecord_swc_subpo_item = [];
      data.customrecord_swc_subpo = [
        {
          internalid: "548",
          name: "子采购001",
          custrecord_swc_subpo_plnum: "70",
          custrecord_swc_subpo_baoguannum: "74",
        },
      ];
    },
  });
  const result = h.query();
  assert.equal(result.complete, true);
  assert.deepEqual(result.groups, []);
  const entries = result.diagnostics.entries;
  assert.ok(entries.some((e) => e.code === "PL_WITHOUT_RAW_HEADERS"));
  const customs = entries.find((e) => e.code === "CUSTOMS_ROWS_OUTSIDE_SOURCE_SCOPE");
  assert.equal(customs.count, 1);
  assert.equal(customs.records[0].id, "622");
  const purchase = entries.find((e) => e.code === "PURCHASE_HEAD_WITHOUT_VISIBLE_LINES");
  assert.equal(purchase.purchaseId, "548");
  assert.equal(purchase.purchaseNumber, "子采购001");
  const xml = load("pl_excel.js", { "./pl_query_service": h.service }).buildParts(result)[
    "xl/worksheets/sheet1.xml"
  ];
  assert.doesNotMatch(xml, /PL_WITHOUT_RAW_HEADERS|子采购001/);
});

test("报关号查询的采购头明细存在但PL关联不在来源范围时，诊断不误报无明细", () => {
  const h = harness({
    changeData(data) {
      data.customrecord_swc_subpo = [
        {
          internalid: "548",
          name: "子采购001",
          custrecord_swc_subpo_plnum: "wrong",
          custrecord_swc_subpo_baoguannum: "74",
        },
      ];
      data.customrecord_swc_subpo_item[0][`${child}.custrecord_swc_subpo_plnum`] = "wrong";
    },
  });
  const result = h.query({ type: "customsRecord", pl: "CD000074" });
  assert.equal(result.complete, true);
  assert.equal(result.counts.purchase, 0);
  const entry = result.diagnostics.entries.find((e) => e.code === "PURCHASE_LINES_OUTSIDE_QUERY");
  assert.deepEqual(entry.lineIds, ["9601"]);
  assert.equal(entry.plId, "wrong");
});

test("补查权限失败只报告补查未完成，不把已有结果改为空或声称子采购不存在", () => {
  const h = harness({ failType: "customrecord_swc_subpo" });
  const result = h.query();
  assert.equal(result.complete, true);
  assert.equal(result.counts.purchase, 1);
  assert.equal(result.groups[0].purchaseRows[0].values.amount, "913");
  const entry = result.diagnostics.entries.find((e) => e.code === "DIAGNOSTIC_READ_FAILED");
  assert.equal(entry.recordType, "customrecord_swc_subpo");
  assert.ok(!result.diagnostics.entries.some((e) => e.code === "PURCHASE_HEAD_NOT_RETURNED"));
  assert.ok(!JSON.stringify(result.diagnostics).includes("字段或权限不允许查询"));
});

test("PL诊断补查不为本次范围外子采购头追加缺明细告警", () => {
  const h = harness({
    changeData(data) {
      data.customrecord_swc_subpo = [
        {
          internalid: "outside",
          name: "范围外采购",
          custrecord_swc_subpo_plnum: "70",
          custrecord_swc_subpo_baoguannum: "195",
        },
      ];
    },
  });
  const result = h.query();
  assert.equal(result.complete, true);
  assert.equal(result.counts.purchase, 1);
  assert.ok(!result.diagnostics.entries.some((e) => e.purchaseId === "outside"));
  assert.ok(
    !h.calls.searches.some(
      (s) =>
        s.searchType === "customrecord_swc_subpo_item" &&
        JSON.stringify(s.filterExpression).includes("outside"),
    ),
  );
});

test("direct配置拒绝汇总或无明细ID，查询失败及两次金额变更不返回部分成功", () => {
  for (const changeConfig of [
    (c) => {
      c.purchase.columns.amount.summary = "SUM";
    },
    (c) => {
      c.purchase.rowKey = ["parentId"];
    },
    (c) => {
      c.traceSources = false;
    },
  ]) {
    const h = harness({ changeConfig });
    const r = h.query();
    assert.equal(r.error.code, "SEARCH_CONFIG_INVALID");
    assert.equal(h.calls.searches.length, 0);
  }
  const failed = harness({ failType: "customrecord_swc_delare_detail" });
  assert.equal(failed.query().complete, false);
  assert.equal(failed.calls.loads, 0);
  const changed = harness({
    legacy: true,
    changeSecondRead: (data) => {
      data.customrecord_swc_subpo_item[0].custrecord_swc_subpo_item_amountwithtax = "900";
    },
  });
  assert.equal(changed.query().error.code, "SOURCE_CHANGED");
});

test("来源追溯的NS原生失败定位读取阶段和操作，不泄漏异常内容或返回部分结果", () => {
  const rawType = "customrecord_swc_declare_line";
  const cases = [
    { recordType: rawType, operation: "runPaged", readPhase: "seed" },
    { recordType: rawType, operation: "runPaged", readPhase: "headers", skip: 1, byPl: true },
    { recordType: rawType, operation: "runPaged", readPhase: "ledger", skip: 1 },
    { recordType: "customrecord_swc_packinglist", operation: "runPaged", readPhase: "packing" },
    { recordType: "salesorder", operation: "runPaged", readPhase: "mother_lines" },
    { recordType: rawType, operation: "create", readPhase: "seed" },
    { recordType: rawType, operation: "fetch", readPhase: "seed" },
    {
      recordType: rawType,
      operation: "createColumn",
      readPhase: "seed",
      fieldName: "custrecord_swc_sl_relate",
    },
    {
      recordType: rawType,
      operation: "getValue",
      readPhase: "seed",
      fieldName: "name",
      join: "custrecord_swc_sl_relate",
    },
    {
      recordType: rawType,
      operation: "getText",
      readPhase: "seed",
      fieldName: "custrecord_swc_packing_main",
    },
  ];
  for (const scenario of cases) {
    let matched = 0;
    const fault = Object.assign(new Error("敏感金额=123456.78; 凭证=secret-token"), {
      name: "SSS_INVALID_SRCH_FILTER",
      code: "IGNORED_SECONDARY_CODE",
      stack: "敏感堆栈 /private/config:123456.78 secret-token",
    });
    const h = harness({
      changeData(data) {
        // 补齐进入母采购行搜索的必要来源键，不依赖任何真实NS记录。
        data.customrecord_swc_packinglist[0].custrecord_swc_sublist_protranid = "50";
      },
      searchFault({ operation, recordType, column }) {
        if (
          operation !== scenario.operation ||
          (operation !== "createColumn" && recordType !== scenario.recordType) ||
          (scenario.fieldName && column?.name !== scenario.fieldName) ||
          (scenario.join && column?.join !== scenario.join)
        )
          return;
        if (matched++ === (scenario.skip || 0)) throw fault;
      },
    });
    const result = h.query(scenario.byPl ? { pl: "PL001" } : { type: "customsRecord", pl: "CD000074" });
    const label = JSON.stringify(scenario);
    assert.equal(result.complete, false, label);
    assert.equal(result.error.code, "QUERY_FAILED", label);
    assert.equal(result.groups, undefined, label);
    assert.equal(result.counts, undefined, label);
    assert.equal(result.error.diagnostic, undefined, "原生失败定位信息仅保留在NS受控日志");
    const logs = h.calls.logs.filter((entry) => entry.title === "PL_QUERY_FAILED");
    assert.equal(logs.length, 1, label);
    const log = JSON.parse(logs[0].details);
    assert.equal(log.stage, "TRACE_SOURCES", label);
    assert.equal(log.code, "QUERY_FAILED", label);
    assert.equal(log.diagnostic.rule, "TRACE_SEARCH_FAILED", label);
    assert.equal(log.diagnostic.recordType, scenario.recordType, label);
    assert.equal(log.diagnostic.readPhase, scenario.readPhase, label);
    assert.equal(log.diagnostic.operation, scenario.operation, label);
    assert.equal(log.diagnostic.errorName, "SSS_INVALID_SRCH_FILTER", label);
    if (scenario.fieldName) assert.equal(log.diagnostic.fieldName, scenario.fieldName, label);
    if (scenario.join) assert.equal(log.diagnostic.join, scenario.join, label);
    assert.doesNotMatch(
      JSON.stringify({ result, logs }),
      /敏感|123456\.78|secret-token|private\/config|IGNORED_SECONDARY_CODE/,
    );
    assert.equal(h.calls.loads, 0, "追溯失败不回退到保存搜索");
    assert.ok(
      !h.calls.searches.some((entry) => entry.searchType === "customrecord_swc_subpo_item"),
      "追溯失败后不继续采购主查询",
    );
  }
});

test("来源追溯异常名只保留合法标识，非法name回退code或UNKNOWN_ERROR", () => {
  for (const [name, code, expected] of [
    ["非法名称\nsecret-token", "INSUFFICIENT_PERMISSION", "INSUFFICIENT_PERMISSION"],
    ["非法名称\nsecret-token", "非法代码 secret-token", "UNKNOWN_ERROR"],
  ]) {
    const h = harness({
      searchFault({ operation, recordType }) {
        if (operation === "runPaged" && recordType === "customrecord_swc_declare_line")
          throw Object.assign(new Error("敏感原始消息 secret-token"), { name, code });
      },
    });
    const result = h.query({ type: "customsRecord", pl: "CD000074" });
    assert.equal(result.complete, false);
    assert.equal(result.error.code, "QUERY_FAILED");
    assert.equal(result.error.diagnostic, undefined);
    const log = JSON.parse(h.calls.logs.at(-1).details);
    assert.equal(log.diagnostic.errorName, expected);
    assert.doesNotMatch(JSON.stringify({ result, logs: h.calls.logs }), /secret-token|非法|敏感/);
  }
});

test("采购一致性失败区分身份、缺行、金额及分页计数，日志与返回诊断一致且不含业务值", () => {
  const cases = [
    [
      "PURCHASE_DETAIL_IDENTITY_CHANGED",
      {
        changeSecondRead: (data) => {
          data.customrecord_swc_subpo_item[0].internalid = "999999";
        },
      },
    ],
    [
      "PURCHASE_DETAIL_MISSING",
      {
        changeSecondRead: (data) => {
          data.customrecord_swc_subpo_item.length = 0;
        },
      },
    ],
    [
      "PURCHASE_DETAIL_AMOUNT_CHANGED",
      {
        changeSecondRead: (data) => {
          data.customrecord_swc_subpo_item[0].custrecord_swc_subpo_item_amountwithtax = "999.99";
        },
      },
    ],
    ...[1, 2].map((read) => [
      read === 1 ? "PRIMARY_COUNT_CHANGED" : "PURCHASE_DETAIL_COUNT_CHANGED",
      {
        changePaged: (paged, type, count) => {
          if (type === "customrecord_swc_subpo_item" && count === read) paged.count += 1;
        },
      },
    ]),
  ];
  for (const [rule, options] of cases) {
    const h = harness({ ...options, legacy: true });
    const result = h.query({ type: "declaration", createdFrom: "2026-08-01", createdTo: "2026-09-22" });
    assert.equal(result.complete, false);
    assert.equal(result.groups, undefined);
    assert.equal(result.error.code, "SOURCE_CHANGED");
    assert.equal(result.error.diagnostic.stage, "PURCHASE_SEARCH");
    assert.equal(result.error.diagnostic.rule, rule);
    const log = JSON.parse(h.calls.logs.at(-1).details);
    assert.deepEqual(log.diagnostic, result.error.diagnostic);
    assert.doesNotMatch(JSON.stringify(log), /999999|999\.99|913|供应商甲|胸章机/);
    if (rule.endsWith("COUNT_CHANGED")) {
      assert.equal(log.diagnostic.expectedCount, 2);
      assert.equal(log.diagnostic.actualCount, 1);
    }
  }
});

test("采购字段失败标明读取阶段和字段，不泄露原值且不返回部分成功", () => {
  const cases = [
    ["primary", "PRIMARY_IDENTITY_MISSING", "internalid", "", "lineId"],
    ["primary", "PRIMARY_PARENT_MISSING", `${child}.internalid`, "", "parentId"],
    ["primary", "FIELD_TEXT_TOO_LONG", "custrecord_swc_subpo_item_bgname", "保密".repeat(151), "name"],
    [
      "primary",
      "NUMERIC_FIELD_INVALID",
      "custrecord_swc_subpo_item_amountwithtax",
      "private-invalid-amount",
      "amount",
    ],
    ["associationDetail", "PURCHASE_DETAIL_ID_MISSING", "internalid", "", "internalid"],
    [
      "associationDetail",
      "FIELD_TEXT_TOO_LONG",
      `${child}.custrecord_swc_subpo_mainpo`,
      "保密".repeat(151),
      "motherKey",
    ],
    [
      "associationDetail",
      "PURCHASE_DETAIL_VALUE_MISSING",
      "custrecord_swc_subpo_item_bgqty",
      null,
      "quantity",
    ],
    [
      "associationDetail",
      "NUMERIC_FIELD_INVALID",
      "custrecord_swc_subpo_item_amountwithtax",
      "private-invalid-amount",
      "amount",
    ],
  ];
  for (const [readPhase, rule, column, value, field] of cases) {
    const change = (data) => {
      data.customrecord_swc_subpo_item[0][column] = value;
    };
    const h = harness(
      readPhase === "primary" ? { changeData: change } : { changeSecondRead: change, legacy: true },
    );
    const result = h.query({ month: "2026-09" });
    assert.equal(result.complete, false);
    assert.equal(result.groups, undefined);
    assert.equal(result.error.code, "SOURCE_DATA_INVALID");
    assert.equal(result.error.diagnostic.stage, "PURCHASE_SEARCH");
    assert.equal(result.error.diagnostic.queryMode, readPhase === "primary" ? "direct" : "savedSearch");
    assert.equal(result.error.diagnostic.rule, rule);
    assert.equal(result.error.diagnostic.readPhase, readPhase);
    assert.equal(result.error.diagnostic.field, field);
    assert.equal(result.error.diagnostic.fieldName, column.split(".").at(-1));
    const log = JSON.parse(h.calls.logs.at(-1).details);
    assert.equal(log.queryMode, readPhase === "primary" ? "direct" : "savedSearch");
    assert.deepEqual(log.diagnostic, result.error.diagnostic);
    assert.doesNotMatch(JSON.stringify(log), /保密|private-invalid-amount|913/);
  }
});

test("采购空金额保留关联及按来源分摊的数量，诊断可定位，零金额仍为零", () => {
  for (const legacy of [false, true]) {
    for (const amount of [null, "", "0"]) {
      const h = harness({
        legacy,
        changeData(data) {
          const p = data.customrecord_swc_subpo_item[0];
          p.custrecord_swc_subpo_item_amountwithtax = amount;
          p.custrecord_swc_subpo_item_qty = "20";
        },
      });
      const result = h.query();
      assert.equal(result.complete, true, JSON.stringify(result.error));
      assert.equal(result.counts.purchase, 1);
      const purchase = result.groups[0].purchaseRows[0];
      assert.equal(purchase.values.quantity, "5");
      assert.equal(purchase.values.unit, "台");
      assert.equal(purchase.values.amount, amount === "0" ? "0" : null);
      assert.equal(purchase.values.price, amount === "0" ? "0.00" : null);
      const diagnostic = result.diagnostics.entries.find((d) => d.code === "PURCHASE_AMOUNT_MISSING");
      assert.equal(Boolean(diagnostic), amount !== "0");
      if (diagnostic) assert.ok(diagnostic.purchaseLineIds.includes("9601"));
      const sheet = load("pl_excel.js", { "./pl_query_service": h.service }).buildParts(result)[
        "xl/worksheets/sheet1.xml"
      ];
      for (const col of ["N", "O"]) {
        const cell = sheet.match(new RegExp(`<c r="${col}3"[^>]*>(.*?)</c>`))[1];
        if (amount !== "0") assert.equal(cell, '<is><t xml:space="preserve"></t></is>');
        else assert.match(cell, /<v>0(?:\.00)?<\/v>/);
      }
    }
  }
});

test("新版配置按月份或跨月创建日期直接读取，不加载旧保存搜索", () => {
  for (const input of [
    { type: "customsRecord", month: "2026-08" },
    { type: "customsRecord", createdFrom: "2026-06-01", createdTo: "2026-09-01" },
  ]) {
    const h = harness({
      changeData: (data) => {
        data.customrecord_swc_declare_record[0].created = "2026-08-17";
        data.customrecord_swc_declare_record[0].custrecord315 = "2026-08-18";
      },
    });
    const result = h.query(input);
    assert.equal(result.complete, true, JSON.stringify(h.calls.logs));
    assert.equal(result.counts.customs, 1);
    assert.equal(result.counts.purchase, 1);
    assert.equal(h.calls.loads, 0);
    assert.equal(JSON.parse(h.calls.logs.at(-1).details).resolution.queryMode, "direct");
  }
});

test("direct同一子采购多个原始行分别追溯后合并，部分关联只分摊对应金额", () => {
  const merged = harness({
    changeData: (data) => {
      data.customrecord_swc_declare_line.push({
        ...data.customrecord_swc_declare_line[0],
        internalid: "2",
        custrecord_swc_packinglist: "2",
        custrecord_swc_fulfillment_line: "2",
      });
      data.customrecord_swc_packinglist.push({
        ...data.customrecord_swc_packinglist[0],
        internalid: "2",
        custrecord_swc_sublist_fulreq_lineid: "2",
        custrecord_swc_so_lineid: "8",
      });
      data.customrecord_swc_subpo_item.push({
        ...data.customrecord_swc_subpo_item[0],
        internalid: "9604",
        custrecord_swc_subpo_item_solineid: "8",
      });
    },
  });
  const r = merged.query();
  assert.equal(r.complete, true, JSON.stringify(merged.calls.logs));
  assert.equal(r.counts.purchase, 1);
  assert.equal(r.groups[0].purchaseRows[0].values.quantity, "20");
  assert.equal(r.groups[0].purchaseRows[0].values.amount, "1826");
  const partial = harness({
    changeData: (data) => {
      data.customrecord_swc_declare_line[0].custrecord_swc_packingqty_2 = "5";
    },
  }).query();
  assert.equal(partial.complete, true);
  assert.equal(partial.groups[0].purchaseRows[0].values.amount, "456.5");
  assert.equal(partial.groups[0].purchaseRows[0].values.quantity, "5");
  assert.equal(partial.groups[0].purchaseRows[0].values.price, "91.30");
});

test("direct保留月份和创建日期范围，无命中不扩大业务查询范围", () => {
  for (const [input, count] of [
    [{ month: "2026-09" }, 1],
    [{ month: "2026-08" }, 0],
    [{ createdFrom: "2026-09-15", createdTo: "2026-09-15" }, 1],
    [{ createdFrom: "2026-09-16", createdTo: "2026-09-30" }, 0],
    [{ month: "2026-08", createdFrom: "2026-09-15", createdTo: "2026-09-15" }, 0],
  ]) {
    const h = harness();
    const r = h.query(input);
    assert.equal(r.complete, true, JSON.stringify(h.calls.logs));
    assert.equal(r.counts.customs, count);
    assert.equal(r.counts.purchase, count);
    assert.equal(h.calls.loads, 0);
  }
});

test("direct一次采购读取同时提供金额和追溯字段，PL、CD及日期查询一致", () => {
  for (const input of [{ pl: "PL001" }, { type: "customsRecord", pl: "CD000074" }, { month: "2026-09" }]) {
    let reads = 0;
    const h = harness({
      changePaged: (_paged, type) => {
        if (type === "customrecord_swc_subpo_item") reads++;
      },
    });
    const result = h.query(input);
    assert.equal(result.complete, true, JSON.stringify(result.error));
    assert.equal(reads, 1);
    assert.equal(result.counts.purchaseAssociationDetails, 1);
    assert.equal(result.groups[0].purchaseRows[0].values.amount, "913");
    assert.equal(result.groups[0].purchaseRows[0].values.quantity, "10");
    assert.equal(result.groups[0].purchaseRows[0].values.unit, "台");
    const columns = h.calls.searches.find((s) => s.searchType === "customrecord_swc_subpo_item").columns;
    assert.ok(columns.some((c) => c.name === "custrecord_swc_subpo_item_solineid"));
    assert.ok(columns.some((c) => c.name === "custrecord_swc_subpo_item_qty"));
    const log = JSON.parse(h.calls.logs.at(-1).details);
    assert.equal(log.serviceVersion, "2026-09-23-missing-purchase-amount-1");
    assert.equal(result.serviceVersion, log.serviceVersion);
    assert.ok(log.performance.some((p) => p.stage === "PURCHASE_SEARCH"));
    assert.ok(log.performance.some((p) => p.stage === "TRACE_SOURCES"));
    assert.ok(log.performance.every((p) => Number.isInteger(p.elapsedMs) && p.elapsedMs >= 0));
  }
});

test("direct仍拒绝缺失追溯数量、分页漏行及仅追溯字段冲突，不返回部分金额", () => {
  const cases = [
    [
      "SOURCE_DATA_INVALID",
      "PURCHASE_DETAIL_VALUE_MISSING",
      {
        changeData: (data) => {
          data.customrecord_swc_subpo_item[0].custrecord_swc_subpo_item_bgqty = null;
        },
      },
    ],
    [
      "SOURCE_DATA_INVALID",
      "FIELD_TEXT_TOO_LONG",
      {
        changeData: (data) => {
          data.customrecord_swc_subpo_item[0].custrecord_swc_subpo_item_solineid = "x".repeat(301);
        },
      },
    ],
    [
      "SOURCE_CHANGED",
      "PRIMARY_COUNT_CHANGED",
      {
        changePaged: (paged, type) => {
          if (type === "customrecord_swc_subpo_item") paged.count++;
        },
      },
    ],
    [
      "SOURCE_ROW_CONFLICT",
      undefined,
      {
        changeData: (data) => {
          data.customrecord_swc_subpo_item.push({
            ...data.customrecord_swc_subpo_item[0],
            custrecord_swc_subpo_item_solineid: "8",
          });
        },
      },
    ],
  ];
  for (const [code, rule, options] of cases) {
    const h = harness(options);
    const result = h.query();
    assert.equal(result.complete, false);
    assert.equal(result.groups, undefined);
    assert.equal(result.error.code, code);
    if (rule) assert.equal(result.error.diagnostic.rule, rule);
    if (code === "SOURCE_DATA_INVALID") assert.equal(result.error.diagnostic.recordId, "9601");
    const log = JSON.parse(h.calls.logs.at(-1).details);
    assert.equal(log.serviceVersion, result.serviceVersion);
    assert.equal(log.stage, "PURCHASE_SEARCH");
    assert.equal(log.performance.at(-1).stage, "PURCHASE_SEARCH");
    assert.ok(log.performance.at(-1).elapsedMs >= 0);
    assert.doesNotMatch(JSON.stringify(log), /xxx|供应商甲|913/);
  }
});

test("direct跨页读取采购只建一份搜索，逐行追溯去重后金额不变", () => {
  let reads = 0;
  const h = harness({
    changeData: (data) => {
      const rows = data.customrecord_swc_subpo_item;
      for (let i = 1; i <= 1000; i++)
        rows.push({
          ...rows[0],
          internalid: String(9601 + i),
          custrecord_swc_subpo_item_item: String(2000 + i),
        });
    },
    changePaged: (_paged, type) => {
      if (type === "customrecord_swc_subpo_item") reads++;
    },
  });
  const result = h.query();
  assert.equal(result.complete, true, JSON.stringify(result.error));
  assert.equal(reads, 1);
  assert.equal(result.counts.purchaseSearch, 1001);
  assert.equal(result.counts.purchaseAssociationDetails, 1001);
  assert.equal(result.counts.purchase, 1);
  assert.equal(result.groups[0].purchaseRows[0].values.amount, "913");
});

test("采购来源零金额的等价写法同时通过主读与追溯，零金额行保留", () => {
  for (const value of ["0.0", ".00", "0E-16", "-0.0000000000000000", " +0.00 "]) {
    const result = harness({
      changeData: (data) => {
        data.customrecord_swc_subpo_item[0].custrecord_swc_subpo_item_amountwithtax = value;
      },
    }).query();
    assert.equal(result.complete, true, JSON.stringify(result.error));
    assert.equal(result.counts.purchase, 1);
    const values = result.groups[0].purchaseRows[0].values;
    assert.equal(Number(values.amount), 0);
    assert.equal(values.quantity, "10");
    assert.equal(values.price, "0.00");
    assert.equal(result.groups[0].customsRows[0].values.amount, "132.74");
  }
});

test("异常金额不当作零或剔除行，失败只输出格式类别和长度", () => {
  for (const [value, format] of [
    ["1,200.00", "COMMA_SEPARATED"],
    ["0.0000000000001", "DECIMAL"],
    ["NaN", "OTHER"],
  ]) {
    const h = harness({
      changeData: (data) => {
        data.customrecord_swc_subpo_item[0].custrecord_swc_subpo_item_amountwithtax = value;
      },
    });
    const result = h.query();
    assert.equal(result.complete, false);
    assert.equal(result.groups, undefined);
    assert.equal(result.error.code, "SOURCE_DATA_INVALID");
    assert.equal(result.error.diagnostic.numericFormat, format);
    assert.equal(result.error.diagnostic.valueLength, value.length);
    assert.doesNotMatch(JSON.stringify(result.error), /1,200|0\.0000000000001|NaN/);
    assert.deepEqual(JSON.parse(h.calls.logs.at(-1).details).diagnostic, result.error.diagnostic);
  }
});
