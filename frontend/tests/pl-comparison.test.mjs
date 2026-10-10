import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { createServer } from "vite";
import { createPlComparisonState } from "./fixtures/pl-comparison.mjs";
let server,
  PlComparison,
  CustomsRows,
  ReviewDialog,
  PlSourceComparison,
  PurchaseRows,
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
    "/src/modules/reconciliation/components/FinanceComparison.tsx",
  ));
  ({ CustomsRows } = await server.ssrLoadModule("/src/modules/reconciliation/components/CustomsRows.tsx"));
  ({ ReviewDialog } = await server.ssrLoadModule("/src/modules/reconciliation/components/ReviewDialog.tsx"));
  ({ PlSourceComparison } = await server.ssrLoadModule(
    "/src/modules/reconciliation/components/PlSourceComparison.tsx",
  ));
  ({ viewPath } = await server.ssrLoadModule("/src/app/paths.ts"));
  ({ navigation } = await server.ssrLoadModule("/src/app/navigation.tsx"));
  ({ PurchaseRows } = await server.ssrLoadModule("/src/modules/reconciliation/components/PurchaseRows.tsx"));
  ({ FinanceSearchForm } = await server.ssrLoadModule(
    "/src/modules/reconciliation/components/FinanceSearchForm.tsx",
  ));
  ({ Pagination } = await server.ssrLoadModule("/src/shared/components/Pagination.tsx"));
});
after(async () => {
  await server?.close();
});
const render = (state = createPlComparisonState()) =>
  renderToStaticMarkup(createElement(PlComparison, { state, onRetry() {}, onFilter() {}, onReview() {} }));
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
const customs = (value, expandedRows = []) =>
  renderToStaticMarkup(
    createElement(CustomsRows, {
      group: value,
      expandedRows,
      toggleRow() {},
      selectLine() {},
    }),
  );

test("采购报关联查与财务核对有两个独立导航和路由", () => {
  const items = navigation.flatMap((section) => section.items);
  assert.equal(items.filter((item) => item.id === "pl").length, 1);
  assert.equal(items.filter((item) => item.id === "finance").length, 1);
  assert.equal(viewPath("pl"), "/pl-reconciliation");
  assert.equal(viewPath("finance"), "/finance-reconciliation");
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
  assert.match(html, /aria-label="审核通过：CDTEST001"/);
  assert.match(html, /aria-expanded="false"/);
  assert.doesNotMatch(html, /SUB-TEST|fr-customs-table|财务审核/);
});
test("明细按后端显式树展示，数量和金额保留原十进制字符串", () => {
  const html = customs(group(), ["customs:0"]);
  for (const text of ["SUB-TEST", "12.5000", "9007199254740993.01", "16.2500", "USD", "CNY"])
    assert.ok(html.includes(text));
  assert.doesNotMatch(html, /财务审核|待审核/);
  const columns = [...html.matchAll(/<colgroup>(.*?)<\/colgroup>/g)].map((match) => match[1]);
  assert.equal(columns.length, 2);
  assert.equal(columns[0], columns[1], "报关行与采购行共用相同列宽");
});
test("第二层默认收起，多个报关单的父子行控制ID独立", () => {
  const a = group(),
    b = { ...group(), id: "102", recordNumber: "CDTEST002" };
  assert.match(customs(a), /aria-expanded="false"/);
  assert.match(customs(a), /hidden="" id="purchases-101-customs:0"/);
  assert.match(customs(b), /aria-controls="purchases-102-customs:0"/);
});
test("后端不允许审核时禁用按钮并展示实际原因", () => {
  const state = createPlComparisonState();
  state.result.groups[0].review = {
    ...state.result.groups[0].review,
    allowed: false,
    status: "blocked",
    label: "待核实",
    reason: "NS未提供明确行关联",
  };
  const html = render(state);
  assert.match(html, /NS未提供明确行关联/);
  assert.match(html, /<button[^>]*disabled=""[^>]*aria-label="审核通过：CDTEST001"/);
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
  const rowHtml = customs(item, ["customs:0"]);
  assert.doesNotMatch(rowHtml, /由财务一并核对|完成关联核实后才可审核|关联子采购明细（|展开关联子采购/);
  assert.doesNotMatch(rowHtml, /associated-purchases|SUB-TEST|aria-expanded/);
  assert.doesNotMatch(customs(item), /SUB-TEST/);
  assert.doesNotMatch(render(createPlComparisonState()), /待核实/);
});

test("点击报关行仅展开该行下的采购，多行独立展开，不混入整单未定位明细", () => {
  const item = group();
  const first = item.customsLines[0];
  first.purchaseLines[0].scope = "order";
  item.customsLines.push({
    ...first,
    id: "customs:1",
    lineNo: 2,
    name: "相纸",
    purchaseLines: [{ ...first.purchaseLines[0], id: "paper", child: "SUB-PAPER", name: "相纸" }],
  });
  item.unlinkedLines = [{ ...first.purchaseLines[0], id: "unknown", child: "UNLOCATED" }];
  const html = customs(item, [first.id]);
  assert.match(html, /<tr id="purchases-101-customs:0"/);
  assert.match(html, /<tr hidden="" id="purchases-101-customs:1"/);
  assert.doesNotMatch(html, /UNLOCATED|associated-purchases|本次采购金额/);
  const firstPurchase = html.indexOf('id="purchases-101-customs:0"');
  const nextCustoms = html.indexOf('aria-controls="purchases-101-customs:1"');
  const firstSection = html.slice(firstPurchase, nextCustoms);
  assert.match(firstSection, /SUB-TEST|订单金额/);
  assert.doesNotMatch(firstSection, /SUB-PAPER/);
  assert.ok(html.indexOf("SUB-PAPER") > nextCustoms);
  const both = customs(item, [first.id, "customs:1"]);
  assert.doesNotMatch(both, /<tr hidden/);
});
test("查询加载、空结果、失败可恢复，后端提示可见", () => {
  assert.match(render({ kind: "idle" }), /填写CD编号/);
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
  assert.match(html, /已入库单据/);
  assert.match(html, /NS production-test/);
  assert.match(html, /aria-expanded="false"/);
  assert.doesNotMatch(html, /重置示例|演示数据|NS读取/);
});

test("未分摊的订单行明确标为子单数量和订单金额，不冒充本次报关范围", () => {
  const html = renderToStaticMarkup(
    createElement(PurchaseRows, {
      lines: group().customsLines[0].purchaseLines,
      label: "测试单",
      scope: "order",
      selectLine() {},
    }),
  );
  assert.match(html, /子单数量/);
  assert.match(html, /订单金额/);
  assert.doesNotMatch(html, /本次数量|本次采购金额|待审核/);
  assert.match(html, /9007199254740993.01/);
});

test("财务搜索使用单一关键字，支持账套选择与刷新", () => {
  const html = renderToStaticMarkup(
    createElement(FinanceSearchForm, {
      accounts: ["prod", "sandbox"],
      busy: false,
      onSearch() {},
      onRefresh() {},
    }),
  );
  assert.match(html, /CD 编号 \/ 真实报关单号 \/ PL \/ 子采购单号 \/ 品名/);
  assert.match(html, /刷新列表/);
  assert.match(html, /全部账套/);
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
