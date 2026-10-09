import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import test from "node:test";
const root = new URL("../SuiteScripts/pl_lookup/", import.meta.url);
const clone = (value) => JSON.parse(JSON.stringify(value));
function load(name, dependencies) {
  let result;
  vm.runInNewContext(readFileSync(new URL(name, root), "utf8"), {
    define: (names, factory) => {
      result = factory(...names.map((name) => dependencies[name]));
    },
  });
  return result;
}
const decimal = load("pl_decimal.js", {});
const fail = (code, diagnostic) => {
  const error = new Error(code);
  error.code = code;
  error.diagnostic = diagnostic;
  throw error;
};
const check = () => {};
const source = (id, extra = {}) => ({
  id: String(id),
  headerId: "74",
  headerNumber: "CD000074",
  plKey: "70",
  pl: "PL-A",
  packingKey: String(id),
  companyKey: "3",
  fulfillmentKey: "216608",
  fulfillmentLineKey: String(id),
  itemKey: "item1",
  name: "转印纸",
  groupUnitKey: "20",
  motherKey: null,
  quantity: "63",
  sourceQuantity: extra.quantity ?? "63",
  unitName: "卷",
  parent: null,
  ...extra,
});
const packing = (id, extra = {}) => ({
  id: String(id),
  plKey: "70",
  fulfillmentKey: "216608",
  fulfillmentLineKey: String(id),
  itemKey: "item1",
  vendorKey: "vendor1",
  motherKey: null,
  salesKey: "SO1",
  salesLineKey: String(id),
  sales: "销售单1",
  companyKey: "3",
  originKey: "city1",
  quantity: "63",
  unitName: "卷",
  taxKey: "1",
  ...extra,
});
const customs = (id, extra = {}) => ({
  rowKey: String(id),
  values: {
    lineId: String(id),
    parentId: "74",
    plKey: "RETAINED_ONLY",
    pl: "汇总保留PL",
    companyKey: "3",
    company: "公司甲",
    name: "转印纸",
    groupUnitKey: "20",
    originKey: "city1",
    vendorKey: "vendor1",
    titleKey: "3",
    amount: "1799.61",
    quantity: "63",
    ...extra,
  },
});
const purchase = (id, sources, extra = {}) => ({
  rowKey: String(id),
  traceSources: sources,
  values: {
    purchase: "子采购" + id,
    quantity: "63",
    amount: "12065.76",
    price: "191.52",
    currency: "CNY",
    name: "转印纸",
    ...extra,
  },
});
const purchaseSource = (id, extra = {}) => {
  const p = packing(id, extra);
  p.id = String(id);
  p.childKey = "child" + id;
  p.amount = "12065.76";
  p.baseQuantity = p.quantity;
  p.unitKey = "20";
  p.isTax = "T";
  delete p.fulfillmentLineKey;
  Object.assign(p, extra);
  return p;
};
function trace(search = {}) {
  return load("pl_trace.js", { "N/search": search, "./pl_decimal": decimal });
}
const ctx = (raw, packs, extra = {}) => ({
  headerIds: ["74"],
  raw,
  packing: packs,
  requestedPl: null,
  ...extra,
});
function group(context, c, p) {
  const service = load("pl_query_service.js", { "./pl_decimal": decimal });
  return clone(trace().group(context, { rows: c }, p, "TEST", check, fail, service.mergePurchaseRows));
}

function searchMock(dataByType, opts = {}) {
  const calls = [];
  function matches(row, expr) {
    if (Array.isArray(expr[0])) return expr.filter((_, i) => i % 2 === 0).every((part) => matches(row, part));
    return expr[1] === "anyof"
      ? expr[2].includes(row[expr[0]])
      : expr[1] === "is" && (row[expr[0]] ?? "F") === expr[2];
  }
  const search = {
    Operator: { ANYOF: "anyof" },
    Sort: { ASC: "ASC" },
    createColumn: (x) => x,
    create: (options) => {
      calls.push(options);
      const rows = (dataByType[options.type] || []).filter((row) => matches(row, options.filters));
      return {
        runPaged: () => ({
          count: opts.count ?? rows.length,
          pageRanges: Array.from({ length: Math.ceil((opts.count ?? rows.length) / 1000) }, (_, index) => ({
            index,
          })),
          fetch: ({ index }) => ({
            data: rows.slice(index * 1000, (index + 1) * 1000).map((row) => ({
              getValue: (col) => row[col.join ? col.join + "." + col.name : col.name],
              getText: (col) => row[col.name],
            })),
          }),
        }),
      };
    },
  };
  return { search, calls };
}
const physicalRaw = (id, pl, header) => ({
  internalid: String(id),
  custrecord_swc_sl_relate: header,
  custrecord_swc_packing_main: pl,
  custrecord_swc_packinglist: String(id),
});
const physicalPacking = (id, pl) => ({ internalid: String(id), custrecord_swc_sublist_packingmain: pl });
test("PL查询先从原始表查单头，再读完整来源及所有PL的Packing，保留跨PL范围", () => {
  const h = searchMock({
    customrecord_swc_declare_line: [
      physicalRaw(1, "70", "74"),
      physicalRaw(2, "80", "74"),
      physicalRaw(3, "90", "75"),
    ],
    customrecord_swc_packinglist: [physicalPacking(1, "70"), physicalPacking(2, "80")],
  });
  const c = clone(trace(h.search).collect({ type: "pl", id: "70" }, "70", "PL-A", check, fail, {}));
  assert.deepEqual(c.headerIds, ["74"]);
  assert.deepEqual(c.plIds, ["70"]);
  assert.equal(c.raw.length, 2);
  assert.equal(c.packing.length, 2);
  assert.equal(h.calls.length, 4);
  assert.deepEqual(clone(h.calls[1].filters[0]), ["custrecord_swc_sl_relate", "anyof", ["74"]]);
  assert.deepEqual(clone(h.calls[2].filters), ["custrecord_swc_sublist_packingmain", "anyof", ["70", "80"]]);
});

test("月份及报关号从单头范围读取原始来源，空解析和空月份不执行全量搜索", () => {
  const h = searchMock({
    customrecord_swc_declare_line: [physicalRaw(1, "70", "74"), physicalRaw(2, "80", "75")],
  });
  const c = clone(
    trace(h.search).collect({ type: "customsRecord", id: "74" }, null, "CD000074", check, fail, {}),
  );
  assert.deepEqual(c.plIds, ["70"]);
  const month = clone(
    trace(h.search).collect({ type: "pl", monthIds: ["74", "75", "76"] }, null, "", check, fail, {}),
  );
  assert.deepEqual(month.headerIds, ["74", "75", "76"]);
  assert.deepEqual(month.plIds, ["70", "80"]);
  const before = h.calls.length;
  for (const [scope, id, num] of [
    [{ type: "pl" }, null, "PL不存在"],
    [{ type: "customsRecord", id: null }, null, "CD不存在"],
    [{ type: "pl", monthIds: [] }, null, ""],
  ]) {
    assert.equal(trace(h.search).collect(scope, id, num, check, fail, {}).headerIds.length, 0);
  }
  assert.equal(h.calls.length, before);
});

test("原始追溯分页、来源重复、数量变化和2000条上限均不返回部分成功", () => {
  const data = {
    customrecord_swc_declare_line: Array.from({ length: 1001 }, (_, i) => physicalRaw(i + 1, "70", "74")),
  };
  const c = trace(searchMock(data).search).collect(
    { type: "customsRecord", id: "74" },
    null,
    "CD000074",
    check,
    fail,
    {},
  );
  assert.equal(c.raw.length, 1001);
  for (const [h, code] of [
    [searchMock(data, { count: 2001 }), "QUERY_TOO_LARGE"],
    [searchMock(data, { count: 1002 }), "SOURCE_CHANGED"],
    [
      searchMock({ customrecord_swc_declare_line: [physicalRaw(1, "70", "74"), physicalRaw(1, "70", "74")] }),
      "SOURCE_ROW_CONFLICT",
    ],
  ]) {
    assert.throws(
      () => trace(h.search).collect({ type: "customsRecord", id: "74" }, null, "CD000074", check, fail, {}),
      (e) => e.code === code,
    );
  }
});

const rows = (groups) => groups.flatMap((g) => g.purchaseRows);
const amountSum = (groups) => rows(groups).reduce((sum, row) => decimal.add(sum, row.values.amount), "0");

test("未关联诊断输出具体字段差异、报关头隔离和汇总候选，不复制金额", () => {
  const c = ctx([source(1, { motherKey: "PO1" })], [packing(1, { motherKey: "PO1", motherLineKey: "7" })]);
  group(
    c,
    [customs(129)],
    [purchase(1, [purchaseSource(1, { motherKey: "PO1", motherLineKey: "8", customsKey: "74" })])],
  );
  const mismatch = c.diagnostics.entries.find((e) => e.code === "PURCHASE_PACKING_UNRESOLVED");
  assert.equal(mismatch.purchaseLineId, "1");
  assert.deepEqual(clone(mismatch.comparisons[0].differences.find((d) => d.field === "motherLineKey")), {
    field: "motherLineKey",
    label: "母采购行号",
    purchase: "8",
    packing: "7",
  });
  assert.ok(!JSON.stringify(c.diagnostics).includes("12065.76"));
  const other = ctx([source(1)], [packing(1)]);
  group(other, [customs(129)], [purchase(1, [purchaseSource(1, { customsKey: "75" })])]);
  assert.ok(!other.diagnostics.entries.some((e) => e.code === "PURCHASE_RAW_OUTSIDE_SCOPE"));
  assert.equal(other.diagnostics.normalExclusions.purchaseLineCount, 1);
  const mismatchHeader = other.diagnostics.entries.find((e) => e.code === "RAW_PURCHASE_HEADER_MISMATCH");
  assert.equal(mismatchHeader.customsId, "74");
  assert.equal(mismatchHeader.otherPurchaseCandidates[0].customsId, "75");
  const ambiguous = ctx([source(1)], [packing(1)]);
  group(ambiguous, [customs(129), customs(130)], [purchase(1, [purchaseSource(1)])]);
  assert.equal(
    ambiguous.diagnostics.entries.find((e) => e.code === "RAW_SUMMARY_UNRESOLVED").candidateCount,
    2,
  );
});

test("其他报关头采购仅计正常排除汇总，不逐行告警且不改变当前关联金额", () => {
  const c = ctx([source(1)], [packing(1)]);
  const valid = purchase(1, [purchaseSource(1, { customsKey: "74" })]);
  const excluded = [2, 3].map((id) =>
    purchase(
      id,
      [
        purchaseSource(1, {
          id: String(id),
          childKey: "526",
          customsKey: "195",
          ...(id === 3 ? { itemKey: "other" } : {}),
        }),
      ],
      { purchase: "同一子采购" },
    ),
  );
  const result = group(c, [customs(129)], [valid, ...excluded]);
  assert.equal(rows(result).length, 1);
  assert.equal(amountSum(result), "12065.76");
  assert.equal(c.diagnostics.normalExclusions.purchaseLineCount, 2);
  assert.equal(c.diagnostics.normalExclusions.purchaseCount, 1);
  assert.ok(!c.diagnostics.entries.some((e) => e.purchaseId === "526"));
  assert.ok(!result[0].warnings.some((w) => w.includes("同一子采购")));
});

test("当前报关头内缺原始来源仍保留诊断，同子采购相同原因合并但明细ID不丢失", () => {
  const c = ctx([], [packing(1)]);
  const purchases = [1, 2].map((id) =>
    purchase(
      id,
      [
        purchaseSource(1, {
          id: String(id),
          childKey: "526",
          customsKey: "74",
        }),
      ],
      { purchase: "同一子采购" },
    ),
  );
  group(c, [customs(129)], purchases);
  const entries = c.diagnostics.entries.filter((e) => e.code === "PURCHASE_RAW_NOT_FOUND");
  assert.equal(entries.length, 1);
  assert.equal(entries[0].lineCount, 2);
  assert.deepEqual(clone(entries[0].purchaseLineIds), ["1", "2"]);
  assert.deepEqual(clone(entries[0].lineDetails.map((d) => d.purchaseLineId)), ["1", "2"]);
  assert.equal(c.diagnostics.normalExclusions, undefined);
});

test("诊断合并按原因和子采购隔离，明细样本超过10条时明确计数", () => {
  const c = ctx([], [packing(1)]);
  const purchases = Array.from({ length: 12 }, (_, i) =>
    purchase(
      i,
      [
        purchaseSource(1, {
          id: String(i),
          childKey: "526",
          customsKey: "74",
        }),
      ],
      { purchase: "采购526" },
    ),
  );
  purchases.push(purchase(20, [purchaseSource(1, { id: "20", childKey: "527", customsKey: "74" })]));
  purchases.push(
    purchase(21, [purchaseSource(1, { id: "21", childKey: "526", customsKey: "74", itemKey: "other" })]),
  );
  group(c, [customs(129)], purchases);
  const entries = c.diagnostics.entries.filter((e) => e.code === "PURCHASE_RAW_NOT_FOUND");
  assert.equal(entries.length, 2);
  const combined = entries.find((e) => e.purchaseId === "526");
  assert.equal(combined.lineCount, 12);
  assert.equal(combined.lineDetails.length, 10);
  assert.equal(combined.omittedLineDetails, 2);
  assert.equal(entries.find((e) => e.purchaseId === "527").lineCount, 1);
  assert.equal(c.diagnostics.entries.find((e) => e.code === "PURCHASE_PACKING_UNRESOLVED").purchaseId, "526");
});

test("空采购诊断覆盖每条无候选原始来源，诊断有数量和体积上限", () => {
  const c = ctx([], []);
  const result = group(
    c,
    Array.from({ length: 130 }, (_, i) => customs(i)),
    [],
  );
  assert.equal(result[0].customsRows.length, 130);
  assert.equal(c.diagnostics.total, 130);
  assert.equal(c.diagnostics.entries.length, 100);
  assert.equal(c.diagnostics.omitted, 30);
  assert.ok(JSON.stringify(c.diagnostics).length < 31000);
  const raw = ctx([source(1)], [packing(1)]);
  group(raw, [customs(129)], []);
  assert.equal(raw.diagnostics.entries.find((e) => e.code === "RAW_WITHOUT_PURCHASE_CANDIDATE").rawId, "1");
});

test("历史行号补救保留来源边界、明确冲突与多候选保护", () => {
  const raw = source(1, { motherKey: "PO1" });
  const pack = packing(1, { motherKey: "PO1", motherLineKey: null });
  const ps = purchaseSource(1, {
    motherKey: "PO1",
    motherLineKey: "7",
    salesLineKey: "12",
    customsKey: "74",
  });
  assert.equal(rows(group(ctx([raw], [pack]), [customs(129)], [purchase(1, [ps])])).length, 1);
  for (const change of [
    { plKey: "other" },
    { motherKey: "other" },
    { itemKey: "other" },
    { companyKey: "other" },
    { fulfillmentKey: "other" },
    { customsKey: "75" },
    { isTax: "F" },
    { packingKey: "missing" },
    { fulfillmentLineKey: "wrong" },
    { motherLineKey: null },
  ]) {
    assert.equal(
      rows(group(ctx([raw], [pack]), [customs(129)], [purchase(1, [{ ...ps, ...change }])])).length,
      0,
      JSON.stringify(change),
    );
  }
  for (const packs of [
    [{ ...pack, motherLineKey: "8" }],
    [{ ...pack, motherLineAmbiguous: true }],
    [pack, { ...pack, id: "2" }],
  ]) {
    assert.equal(rows(group(ctx([raw], packs), [customs(129)], [purchase(1, [ps])])).length, 0);
  }
  const competing = purchase(2, [{ ...ps, id: "second", childKey: "second-child" }]);
  assert.equal(rows(group(ctx([raw], [pack]), [customs(129)], [purchase(1, [ps]), competing])).length, 0);
});

test("历史行号补救按报关头隔离同一Packing，部分查询金额保持一致", () => {
  const first = source(1, { motherKey: "PO1", quantity: "10", summaryKey: "129" });
  const second = { ...first, id: "2", headerId: "75", summaryKey: "130" };
  const packs = [packing(1, { motherKey: "PO1", motherLineKey: null, quantity: "20" })];
  const purchases = ["74", "75"].map((headerId, i) =>
    purchase(i + 1, [
      purchaseSource(1, {
        id: String(i + 1),
        childKey: `child${i + 1}`,
        motherKey: "PO1",
        motherLineKey: "7",
        customsKey: headerId,
        quantity: "10",
        baseQuantity: "10",
        amount: i ? "200" : "100",
      }),
    ]),
  );
  const all = group(
    ctx([first, second], packs, { headerIds: ["74", "75"] }),
    [customs(129), customs(130, { parentId: "75" })],
    purchases,
  );
  assert.deepEqual(
    rows(all).map((r) => r.values.amount),
    ["100", "200"],
  );
  const part = group(
    ctx([second], packs, { headerIds: ["75"], ledger: [first, second] }),
    [customs(130, { parentId: "75" })],
    purchases,
  );
  assert.deepEqual(
    rows(part).map((r) => r.values.amount),
    ["200"],
  );
});

test("同一报关行仅合并母采购、子采购、供应商、品名和单位均相同的来源", () => {
  for (const dimension of [null, "motherKey", "childKey", "vendorKey", "name", "unitKey"]) {
    const packs = [1, 2].map((id) =>
      packing(id, { motherKey: id === 2 && dimension === "motherKey" ? "PO2" : "PO1" }),
    );
    const details = packs.map((p) => source(p.id, { motherKey: p.motherKey }));
    const purchases = packs.map((p, i) =>
      purchase(
        p.id,
        [
          purchaseSource(p.id, {
            packingKey: p.id,
            motherKey: p.motherKey,
            childKey: i && dimension === "childKey" ? "child2" : "child",
            vendorKey: i && dimension === "vendorKey" ? "vendor2" : "vendor",
            unitKey: i && dimension === "unitKey" ? "21" : "20",
          }),
        ],
        { name: i && dimension === "name" ? "另一品名" : "转印纸" },
      ),
    );
    const result = group(ctx(details, packs), [customs(129)], purchases);
    assert.equal(rows(result).length, dimension ? 2 : 1, dimension || "全部相同");
    assert.equal(amountSum(result), "24131.52");
  }
});

test("部分采购数量关联报关：仅显示60/100的数量及金额，余量和金额不生成行", () => {
  const g = group(
    ctx([source(1, { quantity: "60" })], [packing(1, { quantity: "100" })]),
    [customs(129)],
    [purchase(1, [purchaseSource(1, { quantity: "100", amount: "199.99" })])],
  );
  assert.equal(rows(g).length, 1);
  assert.equal(rows(g)[0].values.quantity, "60");
  assert.equal(rows(g)[0].values.amount, "119.99");
  assert.equal(rows(g)[0].values.price, "2.00");
  assert.deepEqual(g[0].displayOrder, [
    { side: "customs", index: 0 },
    { side: "purchase", index: 0, customsIndex: 0 },
  ]);
  assert.equal(g[0].totals.CNY, "119.99");
  assert.equal(g[0].customsRows[0].values.amount, "1799.61");
});

test("同一采购原始行对应多条报关行：先按来源拆分，再分别挂在各报关行下面", () => {
  for (const crossHeader of [false, true]) {
    const detail = [
      source(1, { quantity: "1" }),
      source(2, {
        packingKey: "1",
        fulfillmentLineKey: "1",
        quantity: "2",
        summaryKey: "130",
        headerId: crossHeader ? "75" : "74",
      }),
    ];
    detail[0].summaryKey = "129";
    const g = group(
      ctx(detail, [packing(1, { quantity: "3" })], { headerIds: crossHeader ? ["74", "75"] : ["74"] }),
      [customs(129), customs(130, { parentId: crossHeader ? "75" : "74" })],
      [purchase(1, [purchaseSource(1, { quantity: "3", amount: "10.00" })])],
    );
    assert.equal(rows(g).length, 2);
    assert.deepEqual(
      rows(g).map((r) => r.values.amount),
      ["3.33", "6.67"],
    );
    assert.equal(amountSum(g), "10.00");
    assert.deepEqual(
      g.flatMap((x) => x.displayOrder.map((d) => d.side)),
      ["customs", "purchase", "customs", "purchase"],
    );
  }
});

test("跨查询范围使用全来源累计分摊，分批查询金额与整批一致，未关联部分隐藏", () => {
  const ledger = [
    source(1, { quantity: "1", summaryKey: "129" }),
    source(2, { quantity: "1", packingKey: "1", fulfillmentLineKey: "1", headerId: "75", summaryKey: "130" }),
  ];
  const packs = [packing(1, { quantity: "3" })];
  const purchases = [purchase(1, [purchaseSource(1, { quantity: "3", amount: "0.05" })])];
  const all = group(
    ctx(ledger, packs, { headerIds: ["74", "75"], ledger }),
    [customs(129), customs(130, { parentId: "75" })],
    purchases,
  );
  assert.deepEqual(
    rows(all).map((r) => r.values.amount),
    ["0.02", "0.01"],
  );
  const second = group(
    ctx([ledger[1]], packs, { headerIds: ["75"], ledger }),
    [customs(130, { parentId: "75" })],
    purchases,
  );
  assert.equal(amountSum(second), "0.01");
  assert.equal(amountSum(all), "0.03");
});

test("关联完成后同一子采购单供应商品名单位一致才合并；合并单价按新金额除数量", () => {
  const packs = [packing(1, { quantity: "2" }), packing(2, { quantity: "3" })];
  const details = [source(1, { quantity: "2" }), source(2, { quantity: "3" })];
  const sources = [
    purchaseSource(1, { quantity: "2", amount: "4.01", childKey: "child" }),
    purchaseSource(2, { quantity: "3", amount: "9.00", childKey: "child" }),
  ];
  const g = group(
    ctx(details, packs),
    [customs(129)],
    [purchase(1, [sources[0]]), purchase(2, [sources[1]])],
  );
  assert.equal(rows(g).length, 1);
  assert.equal(rows(g)[0].values.quantity, "5");
  assert.equal(rows(g)[0].values.amount, "13.01");
  assert.equal(rows(g)[0].values.price, "2.60");
  const separate = group(
    ctx(details, packs),
    [customs(129)],
    [purchase(1, [sources[0]]), purchase(2, [sources[1]], { name: "另一品名" })],
  );
  assert.equal(rows(separate).length, 2);
});

test("相同采购内部ID被重复搜索返回不重复分配，内容冲突则拒绝", () => {
  const c = () => ctx([source(1)], [packing(1)]);
  const p = purchase(1, [purchaseSource(1)]);
  assert.equal(rows(group(c(), [customs(129)], [p, clone(p)])).length, 1);
  const conflict = clone(p);
  conflict.traceSources[0].amount = "99";
  assert.throws(() => group(c(), [customs(129)], [p, conflict]), /SOURCE_ROW_CONFLICT/);
});

test("母采购行合并多个Packing来源：按母采购及行号重建，不要求只保留的一组履行引用一致", () => {
  const raw = [
    source(1, { motherKey: "PO1", quantity: "20" }),
    source(2, { motherKey: "PO1", quantity: "30", fulfillmentKey: "F2" }),
  ];
  const packs = [
    packing(1, { motherKey: "PO1", motherLineKey: "7", quantity: "20" }),
    packing(2, {
      motherKey: "PO1",
      motherLineKey: "7",
      quantity: "30",
      fulfillmentKey: "F2",
      salesKey: "SO2",
    }),
  ];
  const ps = purchaseSource(1, { motherKey: "PO1", motherLineKey: "7", quantity: "50", amount: "100" });
  const g = group(ctx(raw, packs), [customs(129)], [purchase(1, [ps])]);
  assert.equal(rows(g)[0].values.quantity, "50");
  assert.equal(amountSum(g), "100");
  const wrong = { ...ps, motherLineKey: "8" };
  assert.equal(rows(group(ctx(raw, packs), [customs(129)], [purchase(1, [wrong])])).length, 0);
});

test("来源身份冲突和Packing重复认领仍不强制匹配", () => {
  for (const [details, packs, purchases] of [
    [[source(1, { itemKey: "wrong" })], [packing(1)], [purchase(1, [purchaseSource(1)])]],
    [
      [source(1)],
      [packing(1)],
      [purchase(1, [purchaseSource(1)]), purchase(2, [purchaseSource(1, { id: "2" })])],
    ],
  ]) {
    const g = group(ctx(details, packs), [customs(129)], purchases);
    assert.equal(rows(g).length, 0);
    assert.match(g[0].warnings.join(" "), /无法|未计入|冲突/);
  }
});

test("原始明细归属歧义不分配；直接报关行引用优先，原字段不覆盖", () => {
  const ambiguous = group(
    ctx([source(1)], [packing(1)]),
    [customs(129), customs(130)],
    [purchase(1, [purchaseSource(1)])],
  );
  assert.equal(rows(ambiguous).length, 0);
  const direct = group(
    ctx([source(1, { summaryKey: "130" })], [packing(1)]),
    [customs(129), customs(130, { originKey: "changed", pl: "NS原PL" })],
    [purchase(1, [purchaseSource(1)])],
  );
  assert.deepEqual(
    direct[0].displayOrder.map((d) => d.side),
    ["customs", "customs", "purchase"],
  );
  assert.equal(direct[0].customsRows[1].values.pl, "NS原PL");
});

test("全部未报关的采购不追加余量行", () => {
  for (const raw of [[]]) {
    const g = group(ctx(raw, [packing(1)]), [customs(129)], [purchase(1, [purchaseSource(1)])]);
    assert.equal(rows(g).length, 0);
    assert.equal(g.length, 1);
    assert.equal(g[0].displayOrder.length, 1);
  }
});

test("按数量比例精确计算支持小数、大金额、负金额；不经过显示单价反算", () => {
  assert.equal(decimal.ratio("199.99", "60", "100", 2), "119.99");
  assert.equal(decimal.ratio("-10", "2", "3", 2), "-6.67");
  assert.equal(decimal.ratio("9007199254740993.01", "0.2", "0.4", 2), "4503599627370496.51");
  assert.equal(
    decimal.ratio("1", "999999999999999999999999999999", "999999999999999999999999999999", 2),
    "1",
  );
  assert.equal(decimal.ratio("1", "1", "0", 2), null);
  assert.equal(decimal.compare("1.00", "1"), 0);
  assert.equal(decimal.subtract("10.00", "6.67"), "3.33");
});

test("母采购行桥接读取完整销售行关系，多个母采购行候选不任取第一条", () => {
  for (const ambiguous of [false, true]) {
    const raw = physicalRaw(1, "70", "74");
    const pack = {
      ...physicalPacking(1, "70"),
      custrecord_swc_sublist_protranid: "PO1",
      custrecord_swc_sublist_createdfrom: "SO1",
      custrecord_swc_so_lineid: "3",
      custrecord_swc_sublist_itemid: "item1",
    };
    const link = {
      internalid: "SO1",
      line: "3",
      item: "item1",
      applyingtransaction: "PO1",
      "applyingTransaction.line": "7",
      "applyingtransaction.type": "PurchOrd",
      mainline: "F",
      taxline: "F",
    };
    const h = searchMock({
      customrecord_swc_declare_line: [raw],
      customrecord_swc_packinglist: [pack],
      salesorder: ambiguous ? [link, { ...link, "applyingTransaction.line": "8" }] : [link, { ...link }],
    });
    const result = trace(h.search).collect(
      { type: "customsRecord", id: "74" },
      null,
      "CD000074",
      check,
      fail,
      {},
    );
    assert.equal(result.packing[0].motherLineKey, ambiguous ? null : "7");
    const query = h.calls.find((c) => c.type === "salesorder");
    assert.ok(query);
    assert.deepEqual(clone(query.filters[0]), ["internalid", "anyof", ["SO1"]]);
    assert.ok(query.columns.every((c) => c.sort === "ASC"));
  }
});

test("Packing直接引用优先且不回退猜测，缺引用可按履行请求行号恢复", () => {
  const c = () => ctx([source(1, { packingKey: null })], [packing(1)]);
  const exact = purchaseSource(1, { packingKey: "1", salesLineKey: "different" });
  assert.equal(rows(group(c(), [customs(129)], [purchase(1, [exact])])).length, 1);
  assert.equal(
    rows(group(c(), [customs(129)], [purchase(1, [{ ...exact, packingKey: "missing" }])])).length,
    0,
  );
  const wrong = purchaseSource(1, { fulfillmentLineKey: "other" });
  assert.equal(rows(group(c(), [customs(129)], [purchase(1, [wrong])])).length, 0);
});

test("公司品名货源地不一致仍不得强制关联", () => {
  for (const override of [{ name: "other" }, { companyKey: "other" }, { originKey: "other" }]) {
    const companyKey = override.companyKey === "1" ? "1" : "3";
    const c = ctx([source(1, { companyKey })], [packing(1, { companyKey })]);
    assert.equal(
      rows(group(c, [customs(129, override)], [purchase(1, [purchaseSource(1, { companyKey })])])).length,
      0,
    );
  }
});

test("税类相异Packing不能并入同一采购来源，分摊仅用同单位数量", () => {
  const raw = [source(1, { quantity: "10" }), source(2, { quantity: "20" })];
  const packs = [
    packing(1, { quantity: "10" }),
    packing(2, { quantity: "20", taxKey: "5", salesLineKey: "1" }),
  ];
  const g = group(
    ctx(raw, packs),
    [customs(129)],
    [purchase(1, [purchaseSource(1, { quantity: "10", amount: "20" })])],
  );
  assert.equal(rows(g)[0].values.quantity, "10");
  assert.equal(amountSum(g), "20");
});

test("逐来源分摊含负金额和极小金额时守恒，完整分摊后不产生额外余量行", () => {
  for (const budget of ["0.01", "-0.01", "10.01", "-10.01"]) {
    const raw = Array.from({ length: 3 }, (_, i) =>
      source(i + 1, { quantity: "1", packingKey: "1", fulfillmentLineKey: "1", summaryKey: String(129 + i) }),
    );
    const g = group(
      ctx(raw, [packing(1, { quantity: "3" })]),
      [customs(129), customs(130), customs(131)],
      [purchase(1, [purchaseSource(1, { quantity: "3", amount: budget })])],
    );
    assert.equal(decimal.compare(amountSum(g), budget), 0);
    assert.equal(rows(g).length, 3);
  }
});

test("500组独立BigInt有理数对照验证比例分摊的舍入与十进制精度", () => {
  let seed = 1729;
  const next = () => {
    seed = (seed * 48271) % 2147483647;
    return seed;
  };
  const money = (cents) =>
    (cents < 0n ? "-" : "") +
    (cents < 0n ? -cents : cents).toString().padStart(3, "0").replace(/(..)$/, ".$1");
  for (let i = 0; i < 500; i++) {
    const cents = BigInt(next()) * 10000001n + BigInt(next() % 100);
    const total = BigInt((next() % 100000) + 1);
    const quantity = BigInt((next() % Number(total)) + 1);
    const unsigned = (cents * quantity * 2n + total) / (total * 2n);
    const sign = i % 2 ? -1n : 1n;
    const result = decimal.ratio(money(sign * cents), quantity.toString(), total.toString(), 2);
    assert.equal(decimal.compare(result, money(sign * unsigned)), 0);
  }
});

test("PL发现单头及全来源分摊台账均排除停用单和停用原始行", () => {
  const h = searchMock({
    customrecord_swc_declare_line: [
      physicalRaw(1, "70", "74"),
      { ...physicalRaw(2, "70", "682"), "custrecord_swc_sl_relate.isinactive": "T" },
      { ...physicalRaw(3, "70", "74"), isinactive: "T" },
    ],
    customrecord_swc_packinglist: [physicalPacking(1, "70")],
  });
  const c = trace(h.search).collect({ type: "pl" }, "70", "PL-A", check, fail, {});
  assert.deepEqual(clone(c.headerIds), ["74"]);
  assert.deepEqual(c.raw.map((r) => r.id).join(","), "1");
  assert.deepEqual(c.ledger.map((r) => r.id).join(","), "1");
});

test("没有直接报关头关联但已匹配采购来源时，显示筛选仍保留报关单", () => {
  const h = searchMock({ customrecord_swc_subpo: [] });
  const g = [{ customsRows: [customs(129, { declaration: null })], purchaseRows: [purchase(1, [])] }];
  const r = trace(h.search).filterIncomplete(g, [{ id: "74", declarationNumber: null }], check, fail);
  assert.equal(r.groups.length, 1);
  assert.equal(r.declarations.length, 1);
  assert.equal(r.hiddenCount, 0);
});

test("报关单位和数量任意调整不影响来源关联及采购金额，包括零申报数量", () => {
  for (const quantity of ["0", "5", "10", "1000"]) {
    const raw = source(1, { quantity, sourceQuantity: "10", unitName: "箱", groupUnitKey: "new" });
    const pack = packing(1, { quantity: "10", unitName: "套" });
    const ps = purchaseSource(1, {
      quantity: "10",
      baseQuantity: "10",
      unitName: "台",
      unitKey: "38",
      amount: "913.00",
    });
    const summary = customs(129, { groupUnitKey: "another", unit: "套", quantity, amount: "132.74" });
    const g = group(ctx([raw], [pack]), [summary], [purchase(1, [ps])]);
    assert.equal(rows(g).length, 1);
    assert.equal(rows(g)[0].values.quantity, "10");
    assert.equal(rows(g)[0].values.unit, "台");
    assert.equal(rows(g)[0].values.amount, "913");
    assert.equal(rows(g)[0].values.price, "91.30");
    assert.equal(g[0].customsRows[0].values.quantity, quantity);
    assert.equal(g[0].customsRows[0].values.amount, "132.74");
  }
});

test("按原始装箱份额分摊采购数量金额，改变申报数量或单位不改变份额", () => {
  const ledger = [
    source(1, { sourceQuantity: "20", quantity: "9999", unitName: "箱", summaryKey: "129" }),
    source(2, {
      packingKey: "1",
      fulfillmentLineKey: "1",
      sourceQuantity: "30",
      quantity: "0",
      unitName: "台",
      headerId: "75",
      summaryKey: "130",
    }),
  ];
  const packs = [packing(1, { quantity: "100" })];
  const purchases = [
    purchase(1, [
      purchaseSource(1, { quantity: "10", baseQuantity: "100", amount: "199.99", unitName: "箱" }),
    ]),
  ];
  const all = group(
    ctx(ledger, packs, { headerIds: ["74", "75"], ledger }),
    [customs(129), customs(130, { parentId: "75" })],
    purchases,
  );
  assert.deepEqual(
    rows(all).map((r) => r.values.quantity),
    ["2", "3"],
  );
  assert.deepEqual(
    rows(all).map((r) => r.values.amount),
    ["40", "60"],
  );
  const second = group(
    ctx([ledger[1]], packs, { headerIds: ["75"], ledger }),
    [customs(130, { parentId: "75" })],
    purchases,
  );
  assert.equal(rows(second)[0].values.amount, "60");
  assert.equal(rows(second)[0].values.quantity, "3");
});

test("历史来源数量缺失或超出采购原数量时仍展示关联，金额留空且不复制总额", () => {
  for (const sourceQuantity of [null, "0", "101"]) {
    const raw = [
      source(1, { quantity: "10", sourceQuantity, summaryKey: "129" }),
      source(2, { packingKey: "1", fulfillmentLineKey: "1", sourceQuantity: "1", summaryKey: "130" }),
    ];
    const g = group(
      ctx(raw, [packing(1, { quantity: "100" })]),
      [customs(129), customs(130)],
      [purchase(1, [purchaseSource(1, { quantity: "100", amount: "913" })])],
    );
    assert.equal(rows(g).length, 2);
    assert.ok(
      rows(g).every((r) => r.values.quantity === null && r.values.amount === null && r.values.price === null),
    );
    assert.match(g[0].warnings.join(" "), /已按来源关联/);
    assert.equal(g[0].totals.CNY, null);
  }
});

test("空金额不阻断其他报关单，合并时不将未知金额当零", () => {
  const context = ctx(
    [
      source(1, { summaryKey: "129" }),
      source(2, { summaryKey: "129" }),
      source(3, { headerId: "75", summaryKey: "130" }),
    ],
    [packing(1), packing(2), packing(3)],
    { headerIds: ["74", "75"] },
  );
  const g = group(
    context,
    [customs(129), customs(130, { parentId: "75" })],
    [
      purchase(1, [purchaseSource(1, { childKey: "shared", amount: null })]),
      purchase(2, [purchaseSource(2, { childKey: "shared", amount: "100" })]),
      purchase(3, [purchaseSource(3, { amount: "126" })]),
    ],
  );
  assert.equal(rows(g).length, 2);
  const unknown = g.find((x) => x.customsRows[0].values.parentId === "74").purchaseRows[0];
  assert.equal(unknown.values.quantity, "126");
  assert.equal(unknown.values.amount, null);
  assert.equal(unknown.values.price, null);
  const normal = g.find((x) => x.customsRows[0].values.parentId === "75").purchaseRows[0];
  assert.equal(normal.values.amount, "126");
  assert.equal(normal.values.price, "2.00");
  assert.equal(g[0].totals.CNY, null);
  assert.ok(context.diagnostics.entries.some((d) => d.code === "PURCHASE_AMOUNT_MISSING"));
});

test("单位不再消除报关汇总候选歧义，有显式报关行引用才唯一归属", () => {
  const raw = source(1);
  const summaries = [customs(129), customs(130, { groupUnitKey: "other" })];
  assert.equal(
    rows(group(ctx([raw], [packing(1)]), summaries, [purchase(1, [purchaseSource(1)])])).length,
    0,
  );
  const g = group(ctx([{ ...raw, summaryKey: "130" }], [packing(1)]), summaries, [
    purchase(1, [purchaseSource(1)]),
  ]);
  assert.deepEqual(
    g[0].displayOrder.map((r) => r.side),
    ["customs", "customs", "purchase"],
  );
});

test("同一Packing分次生成子采购时按子采购报关头隔离，不交叉认领或重复分摊", () => {
  const ledger = [
    source(1, { quantity: "10", sourceQuantity: "10", summaryKey: "129" }),
    source(2, {
      packingKey: "1",
      fulfillmentLineKey: "1",
      headerId: "75",
      quantity: "10",
      sourceQuantity: "10",
      summaryKey: "130",
    }),
  ];
  const packs = [packing(1, { quantity: "10" })];
  const purchases = [
    purchase(1, [purchaseSource(1, { quantity: "10", amount: "100", customsKey: "74" })]),
    purchase(2, [
      purchaseSource(1, { id: "2", childKey: "child2", quantity: "10", amount: "200", customsKey: "75" }),
    ]),
  ];
  const g = group(
    ctx(ledger, packs, { headerIds: ["74", "75"], ledger }),
    [customs(129), customs(130, { parentId: "75" })],
    purchases,
  );
  assert.deepEqual(
    rows(g).map((r) => r.values.amount),
    ["100", "200"],
  );
  const second = group(
    ctx([ledger[1]], packs, { headerIds: ["75"], ledger }),
    [customs(130, { parentId: "75" })],
    purchases,
  );
  assert.equal(rows(second).length, 1);
  assert.equal(rows(second)[0].values.amount, "200");
});

test("Packing直连、母采购行、履行行及销售行追溯均不校验供应商", () => {
  for (const vendorKey of [null, "different-vendor"]) {
    for (const mode of ["packing", "mother", "fulfillment", "sales"]) {
      const raw = source(1, { motherKey: mode === "mother" ? "PO1" : null });
      const pack = packing(1, { motherKey: raw.motherKey, motherLineKey: "7", vendorKey: "packing-vendor" });
      const extra = { vendorKey, motherKey: raw.motherKey };
      if (mode === "packing") extra.packingKey = "1";
      if (mode === "mother") extra.motherLineKey = "7";
      if (mode === "fulfillment") extra.fulfillmentLineKey = "1";
      const ps = purchaseSource(1, extra);
      const g = group(ctx([raw], [pack]), [customs(129)], [purchase(1, [ps], { vendor: "采购供应商原值" })]);
      assert.equal(rows(g).length, 1, mode);
      assert.equal(rows(g)[0].values.amount, "12065.76");
      assert.equal(rows(g)[0].values.vendor, "采购供应商原值");
      // 放宽供应商后仍不能跨货品、公司或PL配对。
      for (const invalid of [{ itemKey: "wrong" }, { companyKey: "wrong" }, { plKey: "wrong" }]) {
        const bad = group(ctx([raw], [pack]), [customs(129)], [purchase(1, [{ ...ps, ...invalid }])]);
        assert.equal(rows(bad).length, 0);
      }
    }
  }
});

test("公司1和5的汇总归属也不核对供应商，供应商不同的采购展示行仍分开合并", () => {
  for (const companyKey of ["1", "5"]) {
    const raw = [source(1, { companyKey, quantity: "10" }), source(2, { companyKey, quantity: "20" })];
    const packs = [
      packing(1, { companyKey, quantity: "10", vendorKey: null }),
      packing(2, { companyKey, quantity: "20", vendorKey: "packing-vendor" }),
    ];
    const purchases = [
      purchase(
        1,
        [
          purchaseSource(1, {
            companyKey,
            packingKey: "1",
            childKey: "same-child",
            quantity: "10",
            amount: "100",
            vendorKey: "vendor-a",
          }),
        ],
        { purchase: "同一子采购单", vendor: "供应商甲" },
      ),
      purchase(
        2,
        [
          purchaseSource(2, {
            companyKey,
            packingKey: "2",
            childKey: "same-child",
            quantity: "20",
            amount: "300",
            vendorKey: "vendor-b",
          }),
        ],
        { purchase: "同一子采购单", vendor: "供应商乙" },
      ),
    ];
    const g = group(ctx(raw, packs), [customs(129, { companyKey, vendorKey: "customs-vendor" })], purchases);
    assert.equal(rows(g).length, 2);
    assert.deepEqual(
      rows(g).map((r) => r.values.vendor),
      ["供应商甲", "供应商乙"],
    );
    assert.equal(amountSum(g), "400");
  }
});

test("移除供应商匹配后出现多个来源候选仍不任意选一条", () => {
  const raw = source(1, { companyKey: "1" });
  const pack = packing(1, { companyKey: "1", vendorKey: "vendor1" });
  const ps = purchaseSource(1, { companyKey: "1", vendorKey: "vendor1" });
  const summaries = [
    customs(129, { companyKey: "1", vendorKey: "vendor1" }),
    customs(130, { companyKey: "1", vendorKey: "vendor2" }),
  ];
  assert.equal(rows(group(ctx([raw], [pack]), summaries, [purchase(1, [ps])])).length, 0);
  const g = group(ctx([{ ...raw, summaryKey: "130" }], [pack]), summaries, [purchase(1, [ps])]);
  assert.deepEqual(
    g[0].displayOrder.map((r) => r.side),
    ["customs", "customs", "purchase"],
  );
});
