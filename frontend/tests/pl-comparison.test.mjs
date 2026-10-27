import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { createServer } from "vite";
import { createPlComparisonState } from "./fixtures/pl-comparison.mjs";
let server,
  PlComparison,
  DeclarationRow,
  BatchApproveDialog,
  CustomsRows,
  ReviewDialog,
  PurchaseDialog,
  PlSourceComparison,
  FinanceSearchForm,
  Pagination,
  viewPath,
  navigation;
// 含应用内链接的组件需要路由上下文。
const inRouter = (element) => createElement(MemoryRouter, null, element);
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  ({ FinanceComparison: PlComparison } = await server.ssrLoadModule(
    "/src/modules/review/components/FinanceComparison.tsx",
  ));
  ({ CustomsRows } = await server.ssrLoadModule("/src/modules/review/components/CustomsRows.tsx"));
  ({ DeclarationRow } = await server.ssrLoadModule("/src/modules/review/components/DeclarationRow.tsx"));
  ({ BatchApproveDialog } = await server.ssrLoadModule(
    "/src/modules/review/components/BatchApproveDialog.tsx",
  ));
  ({ ReviewDialog, PurchaseDialog } = await server.ssrLoadModule(
    "/src/modules/review/components/ReviewDialog.tsx",
  ));
  ({ PlSourceComparison } = await server.ssrLoadModule(
    "/src/modules/source/components/PlSourceComparison.tsx",
  ));
  ({ viewPath } = await server.ssrLoadModule("/src/app/paths.ts"));
  ({ navigation } = await server.ssrLoadModule("/src/app/navigation.tsx"));
  ({ FinanceSearchForm } = await server.ssrLoadModule(
    "/src/modules/review/components/FinanceSearchForm.tsx",
  ));
  ({ Pagination } = await server.ssrLoadModule("/src/shared/components/Pagination.tsx"));
});
after(async () => {
  await server?.close();
});
const render = (state = createPlComparisonState(), props = {}) =>
  renderToStaticMarkup(
    createElement(PlComparison, { state, onRetry() {}, onFilter() {}, onReview() {}, ...props }),
  );
const group = () => createPlComparisonState().result.groups[0];
const pagination = (props = {}) =>
  createElement(Pagination, {
    label: "报关单分页",
    total: 123,
    page: 1,
    pageCount: 7,
    pageSize: 20,
    pageSizes: [10, 20, 50],
    onPageChange() {},
    onPageSizeChange() {},
    ...props,
  });
const customs = (value) =>
  renderToStaticMarkup(
    createElement(CustomsRows, {
      group: value,
      selectLine() {},
    }),
  );

test("采购报关联查与财务核对有两个独立导航和路由", () => {
  const items = navigation.flatMap((section) => section.items);
  assert.equal(items.filter((item) => item.id === "pl").length, 1);
  assert.equal(items.filter((item) => item.id === "finance").length, 1);
  assert.equal(viewPath("pl"), "/pl-reconciliation");
  assert.equal(viewPath("finance"), "/review");
});

test("只读联查保持NS行序、17列与精确金额，不渲染财务审核入口", () => {
  const state = {
    kind: "ready",
    result: {
      contractVersion: 3,
      account: "synthetic",
      readCompletedAt: "2026-09-23T01:00:00Z",
      query: { pl: "CDTEST001" },
      counts: { declarations: 1, customs: 1, purchase: 1 },
      groups: [
        {
          id: "source-1",
          title: "合成来源",
          warnings: ["来源待核实"],
          rows: [
            {
              id: "purchase:0",
              side: "purchase",
              cells: Array.from({ length: 17 }, (_, i) =>
                i === 5 ? "SUB-TEST" : i === 14 ? "9007199254740993.01" : "",
              ),
              note: "NS原始顺序",
              missingCells: [7],
              currency: "CNY",
            },
            {
              id: "customs:0",
              side: "customs",
              cells: Array.from({ length: 17 }, (_, i) => (i === 0 ? "DECLARATION-TEST" : "")),
              note: "",
              missingCells: [],
              currency: "USD",
            },
          ],
        },
      ],
    },
  };
  const html = renderToStaticMarkup(createElement(PlSourceComparison, { state, onRetry() {} }));
  assert.equal((html.match(/scope="col"/g) || []).length, 17);
  assert.ok(html.indexOf("SUB-TEST") < html.indexOf("DECLARATION-TEST"));
  for (const text of ["9007199254740993.01", "CNY", "USD", "来源缺失", "NS原始顺序", "来源待核实"])
    assert.ok(html.includes(text));
  assert.doesNotMatch(html, /审核通过|待审核|aria-expanded/);
  state.result.contractVersion = 1;
  const legacy = renderToStaticMarkup(createElement(PlSourceComparison, { state, onRetry() {} }));
  assert.equal((legacy.match(/scope="col"/g) || []).length, 15);
});
test("默认只展示报关单头，PL及公司同一行且审核按钮位于最高层", () => {
  const html = render();
  assert.match(html, /主报关单（NS 编号）/);
  assert.match(html, /真实报关单号/);
  assert.match(html, /PL-TEST/);
  assert.match(html, /合成申报公司/);
  assert.match(html, /销售单号/);
  assert.match(html, /SO-TEST/);
  assert.match(html, /申报抬头/);
  assert.match(html, /aria-label="审核通过：CDTEST001"/);
  assert.match(html, /aria-expanded="false"/);
  assert.doesNotMatch(html, /SUB-TEST|fr-customs-table|财务审核/);
});
test("明细按后端显式树展示，数量和金额保留原十进制字符串", () => {
  const html = customs(group());
  for (const text of ["SUB-TEST", "12.5000", "9007199254740993.01", "16.2500", "USD", "CNY"])
    assert.ok(html.includes(text));
  assert.doesNotMatch(html, /财务审核|待审核/);
  const tableRows = [...html.matchAll(/<tr\b[^>]*>(.*?)<\/tr>/gs)];
  assert.equal(tableRows.length, 3, "一行公共表头、一行报关、一行采购");
  assert.equal((html.match(/<colgroup>/g) || []).length, 1);
  for (const row of tableRows) assert.equal((row[1].match(/<(?:td|th)\b/g) || []).length, 11);
  assert.match(tableRows[2][0], /data-tone="accent"/);
  // 不单设"来源"列，子采购行在首列缩进挂在报关行下
  assert.doesNotMatch(tableRows[0][1], />来源</);
  assert.match(tableRows[1][1], /fr-tree--customs/);
  assert.match(tableRows[2][1], /fr-tree--purchase/);
  assert.doesNotMatch(html, /aria-expanded|hidden=|fr-purchase-list|<dl/);
});
test("报关行后紧跟它的全部采购行，未关联行保留且明确提示", () => {
  const item = group();
  item.customsLines[0].purchaseLines.push({
    ...item.customsLines[0].purchaseLines[0],
    id: "p2",
    child: "SUB-SECOND",
  });
  item.customsLines.push({
    ...item.customsLines[0],
    id: "customs:1",
    lineNo: 2,
    name: "第二报关商品",
    purchaseLines: [],
    purchaseCount: 0,
  });
  item.unlinkedLines = [{ ...item.customsLines[0].purchaseLines[0], id: "p3", child: "SUB-UNLINKED" }];
  const html = customs(item);
  assert.ok(html.indexOf("SUB-TEST") < html.indexOf("SUB-SECOND"));
  assert.ok(html.indexOf("SUB-SECOND") < html.indexOf("第二报关商品"));
  assert.ok(html.indexOf("第二报关商品") < html.indexOf("SUB-UNLINKED"));
  assert.match(html, /有子采购行尚未关联报关行/);
  assert.doesNotMatch(html, /aria-expanded|<tr[^>]* hidden=/);
});
test("后端不允许审核时禁用按钮并展示实际原因", () => {
  const state = createPlComparisonState();
  state.result.groups[0].review = {
    ...state.result.groups[0].review,
    allowed: false,
    reason: "NS未提供明确行关联",
  };
  const html = render(state, { onBatchApprove() {} });
  assert.match(html, /NS未提供明确行关联/);
  assert.match(html, /<button[^>]*disabled=""[^>]*aria-label="审核通过：CDTEST001"/);
  assert.doesNotMatch(html, /type="checkbox"/, "不可审核的报关单不提供批量勾选");
  assert.match(html, /disabled=""[^>]*>批量审核通过/, "本页没有可审核的报关单时不能进入批量模式");
});

test("状态筛选不再含未出库（拉取时已跳过）；勾选框只在批量模式出现且只对后端允许审核的报关单开放", () => {
  const page = readFileSync(new URL("../src/modules/review/pages/ReviewPage.tsx", import.meta.url), "utf8");
  for (const label of ["全部报关单", "待审核", "审核通过"]) assert.ok(page.includes(label));
  assert.doesNotMatch(page, /未出库/);
  const html = render(createPlComparisonState(), { onBatchApprove() {} });
  assert.doesNotMatch(html, /type="checkbox"/, "点击「批量审核通过」前不显示勾选框");
  assert.match(html, />批量审核通过</);
  assert.doesNotMatch(render(), /批量审核通过/, "未提供批量审核时不显示批量入口");
  const row = (value, checkable) =>
    renderToStaticMarkup(
      createElement(
        "table",
        null,
        createElement(DeclarationRow, {
          group: value,
          open: false,
          checked: false,
          checkable,
          onToggle() {},
          onCheck() {},
          onReview() {},
          onSelectLine() {},
        }),
      ),
    );
  assert.match(row(group(), true), /aria-label="选择报关单：CDTEST001"/);
  assert.doesNotMatch(row(group(), false), /fr-check-cell/, "非批量模式不占勾选列");
  const approved = group();
  approved.review = { ...approved.review, status: "approved" };
  assert.doesNotMatch(row(approved, true), /aria-label="选择报关单/);
});

test("批量审核窗口说明范围仅为当前页已选，并逐张展示跳过原因", () => {
  const groups = [group(), { ...group(), id: "102", recordNumber: "CDTEST002" }];
  const props = { groups, busy: false, error: "", onClose() {}, onApprove() {} };
  const confirm = renderToStaticMarkup(createElement(BatchApproveDialog, { ...props, result: null }));
  assert.match(confirm, /当前页已选 2 张报关单/);
  assert.match(confirm, /不包含其他页或未勾选的报关单/);
  assert.match(confirm, /CDTEST001/);
  assert.match(confirm, /审核通过 2 张/);
  const result = {
    approved: [{ id: "101", recordNumber: "CDTEST001", reason: "" }],
    skipped: [{ id: "102", recordNumber: "", reason: "报关单来源已变化，请刷新后重新核对再审核" }],
  };
  const done = renderToStaticMarkup(createElement(BatchApproveDialog, { ...props, result }));
  assert.match(done, /1 张已审核通过并生成开票任务，1 张未通过/);
  assert.match(done, /CDTEST002[\s\S]*来源已变化/);
  assert.doesNotMatch(done, /审核通过 2 张/);
});
test("保存审核后显示记录入口", () => {
  const state = createPlComparisonState();
  Object.assign(state.result.groups[0].review, {
    status: "approved",
    label: "审核通过",
    allowed: false,
    reviewedBy: "user:admin",
    reviewedAt: "2026-09-23T01:01:00Z",
  });
  assert.match(render(state), /aria-label="查看审核记录：CDTEST001"/);
});
test("审核确认窗口保留来源金额和后端条件", () => {
  const html = renderToStaticMarkup(
    inRouter(
      createElement(ReviewDialog, { group: group(), busy: false, error: "", onClose() {}, onApprove() {} }),
    ),
  );
  assert.ok(html.includes("9007199254740993.01"));
  assert.match(html, /整单审核通过/);
  assert.ok(html.includes("12.5000"));
});
test("财务人工核对包含单头关联的采购行，不增加关联核实步骤", () => {
  const item = group();
  item.unlinkedLines = item.customsLines[0].purchaseLines.map((line) => ({ ...line, scope: "order" }));
  item.customsLines[0].purchaseLines = [];
  item.customsLines[0].purchaseCount = 0;
  const html = renderToStaticMarkup(
    inRouter(
      createElement(ReviewDialog, { group: item, busy: false, error: "", onClose() {}, onApprove() {} }),
    ),
  );
  assert.match(html, /SUB-TEST/);
  assert.match(html, /9007199254740993.01/);
  assert.match(html, /子单数量|订单金额/);
  assert.doesNotMatch(html, /关联核实|重新核实NS/);
  const rowHtml = customs(item);
  assert.doesNotMatch(rowHtml, /由财务一并核对|完成关联核实后才可审核|关联子采购明细（|展开关联子采购/);
  assert.match(rowHtml, /SUB-TEST/);
  assert.match(rowHtml, /未关联报关行的子采购/);
  assert.doesNotMatch(rowHtml, /aria-expanded/);
  assert.doesNotMatch(render(createPlComparisonState()), /待核实/);
});

test("报关单暂无明细时显示明确空状态", () => {
  const item = { ...group(), customsLines: [], unlinkedLines: [] };
  assert.match(customs(item), /暂无报关与采购明细/);
  assert.doesNotMatch(customs(item), /<table|aria-expanded/);
});
test("查询加载、空结果、失败可恢复，后端提示可见", () => {
  assert.match(render({ kind: "idle" }), /填写 CD 编号/);
  assert.match(render({ kind: "loading" }), /正在读取报关单与关联采购/);
  assert.match(render({ kind: "error", message: "连接不可用" }), /连接不可用/);
  assert.match(render({ kind: "error", message: "连接不可用" }), /重新查询/);
  const state = createPlComparisonState();
  state.result.groups = [];
  state.result.notices = ["旧接口缺少行关联"];
  assert.match(render(state), /没有符合条件的报关单/);
  assert.match(render(state), /旧接口缺少行关联/);
});

test("本地自动列表标明来源账套并保持单头收起，不显示演示数据说明", () => {
  const state = createPlComparisonState();
  state.result.source = "database";
  state.result.groups[0].account = "production-test";
  const html = render(state);
  // 数据来源改在页头只读信息中展示
  assert.match(html, /NS production-test/);
  assert.match(html, /aria-expanded="false"/);
  assert.doesNotMatch(html, /重置示例|演示数据|NS读取/);
});

test("订单口径、缺失金额和缺失单位不冒充报关口径或零值", () => {
  const item = group();
  item.customsLines[0].purchaseLines[0] = {
    ...item.customsLines[0].purchaseLines[0],
    scope: "order",
    amount: "",
    unit: "",
  };
  const html = customs(item);
  assert.match(html, /订单口径/);
  assert.match(html, /aria-label="子单数量"/);
  assert.match(html, /aria-label="订单金额"><strong>未提供/);
  assert.doesNotMatch(html, /本次数量|本次采购金额/);
});

test("财务搜索使用单一关键字与供应商筛选，刷新在列表工具条；上线只有正式环境，不提供 NS 账套筛选", () => {
  const html = renderToStaticMarkup(
    createElement(FinanceSearchForm, {
      suppliers: [{ id: "77", name: "合成供应商" }],
      busy: false,
      onSearch() {},
    }),
  );
  assert.match(html, /CD 编号 \/ 真实报关单号 \/ PL \/ 子采购单号 \/ 品名/);
  assert.match(render(), /刷新列表/);
  assert.doesNotMatch(html, /全部账套|来源账套|NS 环境/);
  assert.match(html, /全部供应商/);
  assert.match(html, /<option value="77">合成供应商<\/option>/);
  assert.doesNotMatch(html, /查询方式|重置示例/);
});

test("分页清晰标识当前页并限制首尾翻页和跳转范围", () => {
  const first = renderToStaticMarkup(pagination());
  assert.match(first, /aria-label="上一页"[^>]*disabled=""/);
  assert.match(first, /aria-label="第1页"[^>]*aria-current="page"/);
  assert.match(first, /aria-label="跳转页码，按回车确认"[^>]*min="1"[^>]*max="7"/);
  assert.match(first, /<option value="20" selected="">20条\/页/);
  assert.doesNotMatch(first, /aria-label="下一页"[^>]*disabled/);
  const last = renderToStaticMarkup(pagination({ page: 7 }));
  assert.match(last, /aria-label="下一页"[^>]*disabled=""/);
  assert.match(last, /aria-label="第7页"[^>]*aria-current="page"/);
  assert.doesNotMatch(last, /aria-label="上一页"[^>]*disabled/);
});

test("大量页数保持紧凑导航，当前页和首尾页可访问", () => {
  const html = renderToStaticMarkup(pagination({ total: 100000, page: 2500, pageCount: 5000 }));
  assert.match(html, /aria-label="第1页"/);
  assert.match(html, /aria-label="第2500页"[^>]*aria-current="page"/);
  assert.match(html, /aria-label="第5000页"/);
  assert.ok((html.match(/<button/g) || []).length <= 9);
});

test("空结果仍有总条数，禁用翻页和跳转；加载时禁用所有分页控件", () => {
  const empty = renderToStaticMarkup(pagination({ total: 0, pageCount: 1 }));
  for (const button of empty.matchAll(/<button[^>]*>/g)) assert.match(button[0], /disabled=""/);
  assert.match(empty, /<input[^>]*disabled=""/);
  const busy = renderToStaticMarkup(pagination({ disabled: true }));
  for (const control of busy.matchAll(/<(?:button|input|select)[^>]*>/g))
    assert.match(control[0], /disabled=""/);
  const state = createPlComparisonState();
  state.result.groups = [];
  const html = renderToStaticMarkup(
    createElement(PlComparison, {
      state,
      onRetry() {},
      onFilter() {},
      onReview() {},
      pagination: pagination({ total: 0, pageCount: 1 }),
    }),
  );
  assert.match(html, /没有符合条件的报关单/);
  assert.match(html, /aria-label="报关单分页"/);
  assert.match(html, /共 0 条/);
});

test("币种证据只对后端允许的缺失项开放，已有证据可以完整展示", async () => {
  const { CurrencyEvidenceForm } = await server.ssrLoadModule(
    "/src/modules/review/components/CurrencyEvidenceForm.tsx",
  );
  const checks = [{ purchaseOrderId: "1", orderNumber: "SUB-1", allowed: false, reason: "母单尚未读取" }];
  const blocked = renderToStaticMarkup(
    createElement(CurrencyEvidenceForm, { checks, value: [], busy: false, onChange() {} }),
  );
  assert.match(blocked, /母单尚未读取/);
  assert.match(blocked, /fieldset disabled/);
  assert.doesNotMatch(blocked, /type="checkbox"/);
  const allowed = renderToStaticMarkup(
    createElement(CurrencyEvidenceForm, {
      checks: [{ ...checks[0], allowed: true }],
      value: [{ purchaseOrderId: "1", currency: "CNY", reference: "合同第3页", note: "原件核实" }],
      busy: false,
      onChange() {},
    }),
  );
  assert.match(allowed, /value="CNY"/);
  assert.match(allowed, /合同第3页/);
  assert.match(allowed, /核实说明/);
});

test("任务差异结束遵循后端待复核限制并展示原因", async () => {
  const { DifferenceClosure } = await server.ssrLoadModule(
    "/src/modules/task/components/DifferenceClosure.tsx",
  );
  const html = renderToStaticMarkup(
    createElement(DifferenceClosure, {
      line: { id: "1", close: { allowed: false, reason: "先处理待复核占用" } },
      busy: false,
      onClose() {},
    }),
  );
  assert.match(html, /disabled/);
  assert.match(html, /先处理待复核占用/);
  assert.match(html, /按差异结束/);
});

test("采购合并行展示后端合计，查看弹窗保留原始数量单价金额", () => {
  const item = group();
  const original = item.customsLines[0].purchaseLines[0];
  const merged = {
    ...original,
    id: "group-1",
    quantity: "10",
    amount: "180",
    price: "18",
    members: [
      { ...original, id: "1", quantity: "2", amount: "20", price: "10" },
      { ...original, id: "2", quantity: "8", amount: "160", price: "20" },
    ],
  };
  item.customsLines[0].purchaseLines = [merged];
  assert.match(customs(item), /合并 2 行/);
  const html = renderToStaticMarkup(createElement(PurchaseDialog, { line: merged, onClose() {} }));
  assert.match(html, /合并前采购明细/);
  assert.match(html, /原始数量/);
  assert.match(html, /原含税金额/);
  for (const value of ["180", "160", "20", "18"]) assert.ok(html.includes(value));
});

test("单价异常由后端判定，舍入为零仍突出显示", () => {
  const item = group();
  Object.assign(item.customsLines[0], {
    margin: "0.00%",
    marginStatus: "negative",
    marginNote: "报关单价低于采购价",
    declaredUnitPriceCny: "237.8695",
    combinedPurchaseUnitPrice: "237.87",
  });
  assert.match(customs(item), /data-tone="danger"[\s\S]*报关单价低于采购价/);
  item.customsLines[0].marginStatus = "ok";
  assert.doesNotMatch(customs(item), /data-tone="danger"|报关单价低于采购价/);
});

test("报关行最后一列显示后端计算的申报幅度；负数与无法计算都用文字说明", () => {
  const item = group();
  item.customsLines = [
    {
      ...item.customsLines[0],
      margin: "-12.68%",
      marginStatus: "negative",
      marginNote: "报关单价低于采购价",
      declaredUnitPriceCny: "10.65",
      combinedPurchaseUnitPrice: "12",
    },
    {
      ...item.customsLines[0],
      id: "customs:1",
      lineNo: 2,
      margin: "",
      marginStatus: "unavailable",
      marginNote: "报关行与子采购行单位不一致，不计算申报幅度",
    },
  ];
  const html = customs(item);
  assert.match(html, /申报幅度/);
  assert.match(html, /fr-margin--negative[\s\S]*-12.68%[\s\S]*data-tone="danger"[\s\S]*报关单价低于采购价/);
  assert.match(html, /报关单价 10.65 \/ 合并采购单价 12 元/);
  assert.match(html, /fr-margin--unavailable[\s\S]*—[\s\S]*单位不一致，不计算申报幅度/);
});
