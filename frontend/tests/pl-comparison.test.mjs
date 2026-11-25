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
  ReviewStats,
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
  ({ ReviewDialog } = await server.ssrLoadModule("/src/modules/review/components/ReviewDialog.tsx"));
  ({ PurchaseDialog } = await server.ssrLoadModule("/src/modules/review/components/PurchaseDialog.tsx"));
  ({ PlSourceComparison } = await server.ssrLoadModule(
    "/src/modules/source/components/PlSourceComparison.tsx",
  ));
  ({ viewPath } = await server.ssrLoadModule("/src/app/paths.ts"));
  ({ navigation } = await server.ssrLoadModule("/src/app/navigation.tsx"));
  ({ FinanceSearchForm } = await server.ssrLoadModule(
    "/src/modules/review/components/FinanceSearchForm.tsx",
  ));
  ({ ReviewStats } = await server.ssrLoadModule("/src/modules/review/components/ReviewStats.tsx"));
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
test("单位不一致卡展示后端计数，选中并提交独立筛选", async (t) => {
  const counts = {
    pending: 49,
    changed: 0,
    marginAlert: 22,
    unitMismatch: 8,
    autoApprovable: 18,
    approvedThisMonth: 2,
  };
  let selected;
  const tree = ReviewStats({
    counts,
    value: "unit_mismatch",
    onSelect: (value) => {
      selected = value;
    },
  });
  const cards = tree.props.children;
  assert.deepEqual(
    cards.map((card) => card.props.label),
    ["待审核报关单", "申报幅度异常", "单位不一致", "可自动审核通过", "本月审核通过"],
  );
  cards[2].props.onSelect();
  assert.equal(selected, "unit_mismatch");
  const html = renderToStaticMarkup(tree);
  assert.match(html, /aria-pressed="true"[^]*?单位不一致[^]*?8 张/);
  assert.match(html, /申报幅度异常[^]*?22 张/);
  const calls = [];
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    calls.push(JSON.parse(options.body));
    return Response.json({ groups: [] });
  });
  const { queryDeclarations } = await server.ssrLoadModule("/src/modules/review/api.ts");
  await queryDeclarations({ status: selected, recordNo: "CD870", page: 1, pageSize: 20 });
  assert.equal(calls[0].status, "unit_mismatch");
  assert.equal(calls[0].recordNo, "CD870");
});
test("后台计算未完成时不显示顶部黄色说明，保留审核禁用及原因", () => {
  const state = createPlComparisonState();
  const reason = "来源或审核已更新，后台计算中，请稍后刷新";
  state.result.notices = [reason];
  const item = state.result.groups[0];
  item.calculationStatus = "pending";
  item.review.allowed = false;
  item.review.reason = reason;
  item.marginAlert = false;
  item.autoReview = { eligible: false, reasons: [reason] };
  state.result.groups = [item];
  const html = render(state);
  assert.match(html, /后台计算中，请稍后刷新/);
  assert.doesNotMatch(html, /class="fr-review-reason"/);
  assert.match(html, /disabled=""[^>]*aria-label="审核通过/);
  assert.doesNotMatch(html, />可自动审核<|>申报幅度异常</);
});
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
  assert.doesNotMatch(html, /SUB-TEST|fr-customs-table/);
});

test("财务主行展示后端双审和阻塞原因，有对页权限才定位至同一单号", async () => {
  const { customsDeclarationPath } = await server.ssrLoadModule("/src/app/paths.ts");
  const state = createPlComparisonState();
  const item = state.result.groups[0];
  item.declaration = "REAL&870";
  item.review = { ...item.review, status: "approved", allowed: false };
  item.approvalProgress = {
    finance: { status: "approved", label: "已通过", reason: "" },
    customs: { status: "changed", label: "需重审", reason: "海关回执已换版" },
    status: "waiting_customs",
    label: "等待海关审核",
    reason: "海关回执已换版",
    nextStep: "customs",
    linked: true,
    taskIds: [],
  };
  const props = { state, onRetry() {}, onReview() {} };
  const html = renderToStaticMarkup(
    inRouter(
      createElement(PlComparison, {
        ...props,
        links: { customs: customsDeclarationPath },
      }),
    ),
  );
  assert.match(html, /财务审核.*海关审核.*开票进度.*下一步/);
  assert.match(html, /等待海关审核.*海关回执已换版/);
  assert.match(html, /ui-button--ghost ui-button--sm[^>]*href="\/review\/customs/);
  const expanded = renderToStaticMarkup(
    inRouter(
      createElement(PlComparison, {
        ...props,
        links: { customs: customsDeclarationPath },
        initialExpanded: [item.id],
      }),
    ),
  );
  assert.equal((expanded.match(/>查看对应海关回执</g) ?? []).length, 1);
  item.approvalProgress = { ...item.approvalProgress, nextStep: "import", linked: false };
  const importHtml = renderToStaticMarkup(
    inRouter(createElement(PlComparison, { ...props, links: { customs: customsDeclarationPath } })),
  );
  assert.match(importHtml, /ui-button--ghost ui-button--sm[^>]*>导入海关回执<\/a><button[^>]*>查看记录</);
  assert.doesNotMatch(importHtml, /查看对应海关回执/);
  assert.match(html, /href="\/review\/customs\?exactDeclarationNo=REAL%26870"[^>]*>查看对应海关回执/);
  assert.doesNotMatch(
    renderToStaticMarkup(inRouter(createElement(PlComparison, props))),
    /href="\/review\/customs/,
  );

  item.review = { ...item.review, status: "pending", allowed: true };
  item.approvalProgress = {
    ...item.approvalProgress,
    finance: { status: "pending", label: "待审核", reason: "" },
    customs: { status: "approved", label: "已通过", reason: "" },
    status: "waiting_finance",
    label: "等待财务审核",
    reason: "",
    nextStep: "finance",
    linked: true,
  };
  const financeHtml = renderToStaticMarkup(
    inRouter(createElement(PlComparison, { ...props, links: { customs: customsDeclarationPath } })),
  );
  assert.match(financeHtml, />查看对应海关回执<\/a><button[^>]*>审核财务</);
});

test("已生成任务的财务核对行仅在主行提供单任务入口", () => {
  const item = group();
  item.review = { ...item.review, status: "approved", allowed: false };
  item.approvalProgress = {
    finance: { status: "approved", label: "已通过", reason: "" },
    customs: { status: "approved", label: "已通过", reason: "" },
    status: "created",
    label: "已生成任务",
    reason: "",
    nextStep: "tasks",
    linked: true,
    taskIds: ["308"],
  };
  const renderRow = () =>
    renderToStaticMarkup(
      inRouter(
        createElement(DeclarationRow, {
          group: item,
          open: true,
          checked: false,
          checkable: false,
          onToggle() {},
          onCheck() {},
          onReview() {},
          onSelectLine() {},
          links: { customs: () => "/review/customs", task: (id) => `/tasks/${id}` },
        }),
      ),
    );

  const html = renderRow();
  assert.match(html, /已生成任务/);
  assert.match(html, /href="\/tasks\/308"[^>]*>查看任务</);
  assert.match(html, />查看记录</);
  assert.match(html, /SUB-TEST/);
  assert.doesNotMatch(html, /查看对应海关回执|查看任务 #308|fr-progress-detail/);

  item.approvalProgress.taskIds.push("309");
  const multiple = renderRow();
  assert.match(multiple, /查看任务 #308/);
  assert.match(multiple, /查看任务 #309/);
  assert.doesNotMatch(multiple, /查看对应海关回执/);

  item.approvalProgress.status = "reused";
  assert.match(renderRow(), /查看对应海关回执/);
});

test("主行按后端结果区分单位、数量和实际申报幅度异常", () => {
  for (const [flags, expected] of [
    [{ unitMismatch: true }, ["单位不一致"]],
    [{ quantityMismatch: true }, ["数量不一致"]],
    [{ marginAlert: true }, ["申报幅度异常"]],
    [{ unitMismatch: true, marginAlert: true }, ["单位不一致", "申报幅度异常"]],
    [{}, []],
  ]) {
    const state = createPlComparisonState();
    Object.assign(
      state.result.groups[0],
      { marginAlert: false, unitMismatch: false, quantityMismatch: false },
      flags,
    );
    const html = render(state);
    for (const label of ["单位不一致", "数量不一致", "申报幅度异常"]) {
      assert.equal(html.includes(`>${label}</`), expected.includes(label), label);
    }
    assert.equal(html.includes(" is-alert"), Boolean(flags.marginAlert));
  }
});
test("明细按后端显式树展示，数量和金额保留原十进制字符串", () => {
  const html = customs(group());
  for (const text of ["SUB-TEST", "12.5000", "9007199254740993.01", "16.2500", "USD", "CNY"])
    assert.ok(html.includes(text));
  assert.doesNotMatch(html, /财务审核|待审核/);
  const tableRows = [...html.matchAll(/<tr\b[^>]*>(.*?)<\/tr>/gs)];
  assert.equal(tableRows.length, 3, "一行公共表头、一行报关、一行采购");
  assert.equal((html.match(/<colgroup>/g) || []).length, 1);
  // 原“采购单价”列之外，独立展示后端的采购下单数量。
  for (const row of tableRows) assert.equal((row[1].match(/<(?:td|th)\b/g) || []).length, 13);
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
  assert.match(done, /1 张已通过财务审核，1 张未通过。\s*关闭后可在列表查看各单的开票进度/);
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
test("查询加载、空结果、失败可恢复，列表不再渲染顶部说明条", () => {
  assert.match(render({ kind: "idle" }), /填写 CD 编号/);
  assert.match(render({ kind: "loading" }), /正在读取报关单与关联采购/);
  assert.match(render({ kind: "error", message: "连接不可用" }), /连接不可用/);
  assert.match(render({ kind: "error", message: "连接不可用" }), /重新查询/);
  const state = createPlComparisonState();
  state.result.groups = [];
  state.result.notices = ["旧接口缺少行关联"];
  assert.match(render(state), /没有符合条件的报关单/);
  assert.doesNotMatch(render(state), /旧接口缺少行关联/);
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

test("财务搜索包含申报抬头等五个批量输入框，上方显示标签", () => {
  const html = renderToStaticMarkup(
    createElement(FinanceSearchForm, {
      suppliers: [{ id: "77", name: "合成供应商" }],
      busy: false,
      onSearch() {},
    }),
  );
  assert.equal((html.match(/type="search"/g) || []).length, 5);
  assert.equal((html.match(/type="date"/g) || []).length, 2);
  assert.match(html, /name="declarationNo"/);
  assert.match(html, /name="declarantName"/);
  assert.match(html, /报关单创建日期 从/);
  assert.match(html, /name="createdFrom"/);
  assert.match(html, /name="createdTo"/);
  // 2026-11-09 起查询栏与进项发票列表一致，标签显示在输入框上方
  for (const label of ["供应商", "申报抬头", "CD 号", "报关单号", "子采购单号"]) {
    assert.ok(html.includes(`<span>${label}</span>`));
  }
  assert.doesNotMatch(html, /ui-sr-only/);
  assert.match(render(), /刷新列表/);
  assert.doesNotMatch(html, /全部账套|来源账套|NS 环境/);
  assert.match(html, /多条用逗号分隔/);
  assert.doesNotMatch(html, /<select|查找报关与采购单据/);
  assert.doesNotMatch(html, /查询方式|重置示例/);
});

test("财务日期筛选原样传给后端，清空后提交 null 恢复不限", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    calls.push(JSON.parse(options.body));
    return Response.json({ groups: [] });
  });
  const { queryDeclarations } = await server.ssrLoadModule("/src/modules/review/api.ts");
  await queryDeclarations({
    declarantName: "上海毅鑫",
    createdFrom: "2026-08-01",
    createdTo: "2026-08-31",
    page: 1,
  });
  await queryDeclarations({ declarantName: "", createdFrom: "", createdTo: "", page: 1 });
  assert.equal(calls[0].declarantName, "上海毅鑫");
  assert.equal(calls[1].declarantName, "");
  assert.equal(calls[0].createdFrom, "2026-08-01");
  assert.equal(calls[0].createdTo, "2026-08-31");
  assert.equal(calls[1].createdFrom, null);
  assert.equal(calls[1].createdTo, null);
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

test("采购查看弹窗原样显示销售订单汇率，缺失时不显示默认汇率", () => {
  const line = group().customsLines[0].purchaseLines[0];
  const detail = (rate) =>
    renderToStaticMarkup(
      createElement(PurchaseDialog, {
        line: { ...line, salesOrderExchangeRate: rate },
        onClose() {},
      }),
    );
  assert.match(detail("6.712345678901"), /<dt>销售订单汇率<\/dt><dd>6\.712345678901<\/dd>/);
  for (const rate of ["", undefined]) {
    assert.match(detail(rate), /<dt>销售订单汇率<\/dt><dd>来源未提供<\/dd>/);
  }
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
  assert.match(html, /报关数量/);
  assert.match(html, /原含税金额/);
  assert.match(html, /可上下及横向滚动/);
  for (const value of ["180", "160", "20", "18"]) assert.ok(html.includes(value));
});

test("采购详情字段独立对应，保留零值和缺失值，不虚构原始行", () => {
  const original = group().customsLines[0].purchaseLines[0];
  const html = renderToStaticMarkup(
    createElement(PurchaseDialog, {
      line: { ...original, scope: "order", quantity: "0", unit: "千克", price: "0", amount: "", members: [] },
      onClose() {},
    }),
  );
  assert.match(html, /<dt>子单数量<\/dt><dd>0<\/dd>/);
  assert.match(html, /<dt>单位<\/dt><dd>千克<\/dd>/);
  assert.match(html, /<dt>采购含税单价（金额 ÷ 展示数量）<\/dt><dd>0<\/dd>/);
  assert.match(html, /<dt>订单含税金额（未分摊）<\/dt><dd>来源未提供<\/dd>/);
  assert.doesNotMatch(html, /<table/);
});

test("单价异常由后端判定，舍入为零仍突出显示", () => {
  const item = group();
  Object.assign(item.customsLines[0], {
    margin: "0.00%",
    marginStatus: "negative",
    marginNote: "报关单价低于不含税采购单价",
    declaredUnitPriceCny: "237.8695",
    originalUnitPriceCny: "237.87",
  });
  assert.match(customs(item), /data-tone="danger"[\s\S]*报关单价低于不含税采购单价/);
  item.customsLines[0].marginStatus = "ok";
  item.customsLines[0].margin = "-0.01%";
  item.customsLines[0].marginNote = "精度范围内一致（人民币单价差额 0.0305 元，容差 0.10 元）";
  assert.doesNotMatch(customs(item), /data-tone="danger"|报关单价低于不含税采购单价/);
  assert.match(customs(item), /精度范围内一致/);
  assert.match(customs(item), /-0.01%/);
});

test("报关行最后一列显示后端计算的申报幅度；负数与无法计算都用文字说明", () => {
  const item = group();
  item.customsLines = [
    {
      ...item.customsLines[0],
      margin: "-12.68%",
      marginStatus: "negative",
      marginNote: "报关单价低于不含税采购单价",
      declaredUnitPriceCny: "10.65",
      originalUnitPriceCny: "12",
      declaredUnitPriceUsd: "1.5",
      purchaseUnitPriceUsd: "1.690141",
      originalPriceUnit: "箱",
      declaredPriceUnit: "个",
    },
    {
      ...item.customsLines[0],
      id: "customs:1",
      lineNo: 2,
      margin: "",
      marginStatus: "unavailable",
      marginNote: "采购单价缺失，无法计算申报幅度",
    },
  ];
  const html = customs(item);
  assert.match(html, /申报幅度/);
  assert.match(
    html,
    /fr-margin--negative[\s\S]*-12.68%[\s\S]*data-tone="danger"[\s\S]*报关单价低于不含税采购单价/,
  );
  assert.doesNotMatch(html, /报关单价 1.5|不含税采购单价 1.690141|未税金额合计 ÷/);
  assert.match(html, /fr-margin--unavailable[\s\S]*—[\s\S]*采购单价缺失，无法计算申报幅度/);
});

test("采购未税 USD 单价独立展示；单位或数量不一致仅阻止幅度", () => {
  const item = group();
  item.customsLines = [
    {
      ...item.customsLines[0],
      originalQuantity: "10332",
      originalPriceUnit: "盒",
      declaredPriceUnit: "平方米",
      originalPrice: "999",
      purchaseUnitPriceUsd: "0.940431",
      purchaseOrderQuantity: "15000",
      purchasePriceNote: "关联采购未税金额 / 采购下单数量，再按销售单汇率折 USD",
      margin: "",
      marginStatus: "unit_mismatch",
      marginNote: "原始单位“盒”与报关单位“平方米”不一致，不计算申报幅度",
    },
    {
      ...item.customsLines[0],
      id: "customs:1",
      lineNo: 2,
      originalPrice: "",
      originalPriceUnit: "",
      margin: "",
      marginStatus: "quantity_mismatch",
      marginNote: "原始数量 17000 与报关数量 17687.33 不一致，不计算申报幅度",
    },
  ];
  const html = customs(item);
  // 采购下单数量独立成列，金额、采购数量、采购价与幅度连续展示。
  assert.match(
    html,
    /<th[^>]*>金额<\/th><th[^>]*>采购数量<\/th><th[^>]*>未含税采购单价<\/th><th[^>]*>申报幅度<\/th>/,
  );
  assert.match(html, /aria-label="未含税采购单价，美元"[^>]*>0.94<\/span>/);
  assert.match(html, /aria-label="关联采购下单数量合计">15000<\/span>/);
  assert.doesNotMatch(html, /USD \/ 盒|下单数量 15000|采购单价（未税 USD）|申报幅度（单价）/);
  assert.doesNotMatch(html, /含税价 ÷ 1.13|>999<small> USD/);
  assert.match(html, /title="原始单位“盒”与报关单位“平方米”不一致，不计算申报幅度"/);
  assert.match(html, /aria-label="原始单位“盒”与报关单位“平方米”不一致，不计算申报幅度"/);
  assert.match(html, /title="原始数量 17000 与报关数量 17687.33 不一致，不计算申报幅度"/);
  assert.match(html, /data-tone="warning"[^>]*>单位不一致<\/span>/);
  assert.match(html, /<small>报关：平方米<\/small><small>采购：盒<\/small>/);
  assert.match(html, /data-tone="warning"[^>]*>数量不一致<\/span>/);
  assert.doesNotMatch(html, /<small>原始单位|<small>原始数量/);
  assert.match(html, /aria-label="未含税采购单价，美元"[^>]*>未提供<small>等待后台计算<\/small>/);
});

test("单位不一致提示保留两种单位，采购单位缺失不借用报关单位", () => {
  const item = group();
  Object.assign(item.customsLines[0], {
    marginStatus: "unit_mismatch",
    declaredPriceUnit: "千克",
    originalPriceUnit: "包、箱",
    marginNote: "采购下单单位与报关单位不一致，不计算申报幅度",
  });
  assert.match(customs(item), /<small>报关：千克<\/small><small>采购：包、箱<\/small>/);
  item.customsLines[0].originalPriceUnit = "";
  assert.match(customs(item), /<small>报关：千克<\/small><small>采购：未提供<\/small>/);
});

test("对照表单价显示两位小数，十进制四舍五入不丢精度、不修改来源", () => {
  const item = group();
  const line = item.customsLines[0];
  line.price = "1";
  line.purchaseLines[0].price = "0";
  for (const [source, displayed] of [
    ["2.184869", "2.18"],
    ["0.2356", "0.24"],
    ["1.005", "1.01"],
    ["9.999", "10.00"],
    ["0", "0.00"],
    ["9007199254740993.125", "9007199254740993.13"],
  ]) {
    line.purchaseUnitPriceUsd = source;
    const html = customs(item);
    assert.ok(html.includes(`aria-label="未含税采购单价，美元">${displayed}</span>`));
    assert.match(html, /aria-label="申报单价">1.00<\/span>/);
    assert.match(html, /aria-label="采购含税单价">0.00/);
    assert.equal(line.purchaseUnitPriceUsd, source);
    assert.equal(line.price, "1");
    assert.equal(line.purchaseLines[0].price, "0");
  }
});

test("采购数量独立显示后端下单口径，缺失不借用报关数量", () => {
  const item = group();
  const line = item.customsLines[0];
  line.quantity = "500";
  line.purchaseOrderQuantity = "920";
  line.purchaseLines[0].quantity = "500";
  line.purchaseLines[0].purchaseQuantity = "920";
  let html = customs(item);
  assert.match(html, /aria-label="申报数量">500<\/span>/);
  assert.match(html, /aria-label="关联采购下单数量合计">920<\/span>/);
  assert.match(html, /aria-label="采购下单数量">920<\/span>/);
  line.purchaseOrderQuantity = "";
  line.purchaseLines[0].purchaseQuantity = "";
  html = customs(item);
  assert.match(html, /aria-label="关联采购下单数量合计">未提供<\/span>/);
  assert.match(html, /aria-label="采购下单数量">未提供<\/span>/);
});

test("NS 未填申报单价时显示后端试算值并标注“试算”，不在前端计算", () => {
  const item = group();
  item.customsLines = [
    {
      ...item.customsLines[0],
      price: "1.5",
      priceEstimated: true,
      margin: "-12.68%",
      marginStatus: "negative",
      marginNote: "报关单价低于不含税采购单价",
      declaredUnitPriceCny: "10.65",
      originalUnitPriceCny: "12",
      declaredUnitPriceUsd: "1.5",
      purchaseUnitPriceUsd: "1.690141",
      originalPriceUnit: "箱",
      declaredPriceUnit: "个",
    },
    { ...item.customsLines[0], id: "customs:1", lineNo: 2, price: "1.5", priceEstimated: false },
  ];
  const html = customs(item);
  assert.match(
    html,
    /aria-label="申报单价 1.50，NS 未填写，按报关金额除以报关数量试算"[^>]*>1.50<span class="ui-badge" data-tone="info">试算<\/span>/,
  );
  assert.doesNotMatch(html, /报关单价 1.5 USD|不含税采购单价 1.690141|未税金额合计 ÷/);
  assert.equal(html.match(/>试算</g).length, 1);
});

test("子采购单价保留两位小数并使用展示数量单位", () => {
  const item = group();
  const line = {
    ...item.customsLines[0].purchaseLines[0],
    scope: "declared",
    quantity: "1525",
    unit: "平方米",
    price: "5.32",
    purchaseQuantity: "100",
    purchaseUnit: "卷",
    amount: "8113",
  };
  item.customsLines[0].purchaseLines = [line];
  const html = customs(item);
  assert.match(html, /子采购报关数量[^>]*>1525/);
  assert.match(html, /平方米/);
  assert.match(html, /采购含税单价[^>]*>5.32<small> \/ 平方米/);
  assert.doesNotMatch(html, /订单口径/);
  const detail = renderToStaticMarkup(createElement(PurchaseDialog, { line, onClose() {} }));
  assert.match(detail, /采购数量<\/dt><dd>100/);
  assert.match(detail, /采购单位<\/dt><dd>卷/);
  assert.match(detail, /采购含税单价（金额 ÷ 展示数量）<\/dt><dd>5.32/);
});

test("子采购合并行与详情保留后端单价尾零", () => {
  const item = group();
  const member = {
    ...item.customsLines[0].purchaseLines[0],
    scope: "declared",
    quantity: "17687.33",
    unit: "平方米",
    purchaseUnit: "卷",
    price: "13.70",
    amount: "242310.6",
  };
  const line = { ...member, members: [member] };
  item.customsLines[0].purchaseLines = [line];
  assert.match(customs(item), /采购含税单价[^>]*>13.70<small> \/ 平方米/);
  const detail = renderToStaticMarkup(createElement(PurchaseDialog, { line, onClose() {} }));
  assert.match(detail, /13.70 \/ 平方米/);
  assert.doesNotMatch(detail, /13.70 \/ 卷/);
});

test("数量不一致时只展示数量提示，不显示单价异常或旧幅度", () => {
  const item = group();
  item.marginAlert = false;
  Object.assign(item.customsLines[0], {
    margin: "",
    marginStatus: "quantity_mismatch",
    marginNote: "数量不一致（报关行 24965.5，子采购报关合计 41260）",
    originalUnitPriceCny: "",
    declaredUnitPriceCny: "",
  });
  const html = customs(item);
  assert.match(html, /数量不一致（报关行 24965.5，子采购报关合计 41260）/);
  assert.match(html, /data-tone="warning"[^>]*>数量不一致/);
  assert.doesNotMatch(html, /单价异常|报关单价低于不含税采购单价|data-tone="danger"|-65.59%/);
});

test("采购单价缺失时保留原因，不显示低价异常或旧幅度", () => {
  const item = group();
  Object.assign(item.customsLines[0], {
    margin: "",
    marginStatus: "unavailable",
    marginNote: "采购单价缺失，无法计算申报幅度",
    declaredUnitPriceCny: "",
    originalUnitPriceCny: "",
  });
  const html = customs(item);
  assert.match(html, /采购单价缺失，无法计算申报幅度/);
  assert.doesNotMatch(html, /单价异常|报关单价低于不含税采购单价|fr-margin--negative/);
});

test("海关明细同时显示 NS 报关行总价和回执成交总价，差异时标注", async () => {
  const { CustomsCompareTable } = await server.ssrLoadModule(
    "/src/modules/review/components/CustomsCompareTable.tsx",
  );
  const group = {
    status: "matched",
    label: "一致",
    consistent: true,
    note: "数量 3189 千克",
    nsLines: [{ id: 2, name: "相纸", currency: "USD", total: "5416.26" }],
    items: [{ itemNo: "02", name: "相纸", currency: "USD", total: "5416.25" }],
  };
  const render = (totalMismatch) =>
    renderToStaticMarkup(
      createElement(CustomsCompareTable, {
        declarationNo: "REAL870",
        groups: [{ ...group, totalMismatch }],
      }),
    );
  assert.match(render(true), /USD 5416\.26/);
  assert.match(render(true), /USD 5416\.25/);
  assert.match(render(true), /总价不一致/);
  assert.doesNotMatch(render(false), /总价不一致/);
  assert.doesNotMatch(render(false), /数量 3189 千克/);
});

test("海关审核只提交当前页选择的版本令牌、方式与人工说明", async () => {
  const { approveCustomsReceipts } = await server.ssrLoadModule("/src/modules/review/customs-api.ts");
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, body: JSON.parse(init.body) });
    return new Response(
      JSON.stringify({ approved: [{ id: 17, declarationNo: "REAL17", reason: "" }], skipped: [] }),
    );
  };
  try {
    const result = await approveCustomsReceipts(
      [{ id: 17, approval: { token: "a".repeat(64) }, status: "different" }],
      "已核实差异",
    );
    assert.equal(result.approved.length, 1);
    assert.deepEqual(calls, [
      {
        url: "/api/review/customs-receipts/approve-batch",
        body: {
          items: [{ id: 17, token: "a".repeat(64) }],
          method: "manual",
          note: "已核实差异",
        },
      },
    ]);
  } finally {
    globalThis.fetch = original;
  }
});

test("海关人工审核确认明确当前页范围与双审核开票门槛", async () => {
  const { CustomsApproveDialog } = await server.ssrLoadModule(
    "/src/modules/review/components/CustomsApproveDialog.tsx",
  );
  const html = renderToStaticMarkup(
    createElement(CustomsApproveDialog, {
      items: [{ id: 17, declarationNo: "REAL17", statusLabel: "拆行一致" }],
      onClose() {},
      onChanged() {},
    }),
  );
  assert.match(html, /当前页选定的 1 张回执/);
  assert.match(html, /海关与财务两项当前版本均审核通过后/);
  assert.match(html, /人工审核说明/);
  assert.doesNotMatch(html, /自动审核当前页|自动审核只通过/);
  assert.match(html, /确认审核通过/);
  assert.match(html, /REAL17/);
});

test("海关审核行复用财务勾选与主按钮样式，移除重新匹配操作", async () => {
  const { CustomsReceiptRow } = await server.ssrLoadModule(
    "/src/modules/review/components/CustomsReceiptRow.tsx",
  );
  const receipt = {
    id: 17,
    declarationNo: "TEST-17",
    exportDate: "2026-11-13",
    taxType: "征税",
    customsDoc: "存在",
    usageFlag: "未使用",
    nsLineCount: 1,
    itemCount: 1,
    nsRecordNo: "CDTEST17",
    consignee: { state: "empty", label: "回执未提供", value: "", note: "" },
    status: "matched",
    statusLabel: "一致",
    statusNote: "",
    totalComparison: "matched",
    groups: [],
    approval: { approved: false, label: "待审核", allowed: true, autoAllowed: true, reason: "" },
  };
  const props = {
    receipt,
    open: false,
    busy: false,
    batch: true,
    selected: true,
    onToggle() {},
    onSelect() {},
    onApprove() {},
  };
  const html = renderToStaticMarkup(createElement(CustomsReceiptRow, props));
  assert.match(html, /总价一致/);
  assert.match(
    renderToStaticMarkup(
      createElement(CustomsReceiptRow, { ...props, receipt: { ...receipt, totalComparison: "different" } }),
    ),
    /总价不一致/,
  );
  assert.match(html, /fr-declaration-row is-checked/);
  assert.match(html, /class="fr-check-cell"/);
  assert.match(html, /type="checkbox"[^>]*checked/);
  assert.match(html, /ui-button--primary/);
  assert.match(html, /aria-label="审核通过：TEST-17"/);
  assert.doesNotMatch(html, /重新匹配|选本页/);
  const pending = { status: "pending", label: "待审核", reason: "" };
  const linked = renderToStaticMarkup(
    inRouter(
      createElement(CustomsReceiptRow, {
        ...props,
        open: true,
        links: { finance: (number) => "/review?exactDeclarationNo=" + number },
        receipt: {
          ...receipt,
          approvalProgress: {
            finance: pending,
            customs: pending,
            status: "waiting_both",
            label: "待双审",
            reason: "",
            nextStep: "both",
            linked: true,
            taskIds: [],
          },
        },
      }),
    ),
  );
  const rowActions = linked.match(/<div class="fr-next-action">(.*?)<\/div>/)?.[1] ?? "";
  assert.match(rowActions, /ui-button--primary[^>]*>审核通过</);
  assert.match(
    rowActions,
    /ui-button--ghost ui-button--sm[^>]*href="\/review\?exactDeclarationNo=TEST-17"[^>]*>查看对应财务核对</,
  );
  assert.equal((linked.match(/>查看对应财务核对</g) ?? []).length, 1);
  const blocked = renderToStaticMarkup(
    createElement(CustomsReceiptRow, {
      ...props,
      selected: false,
      receipt: {
        ...receipt,
        approval: {
          ...receipt.approval,
          allowed: false,
          autoAllowed: false,
          reason: "须先唯一匹配到 NS 报关单",
        },
      },
    }),
  );
  assert.doesNotMatch(blocked, /type="checkbox"/);
  assert.match(blocked, /须先唯一匹配到 NS 报关单/);
  assert.match(blocked, /<button[^>]*disabled[^>]*aria-label="审核通过：TEST-17"/);
});

test("海关人工审核说明独立成行，输入框关联标签与说明", async () => {
  const { CustomsApproveDialog } = await server.ssrLoadModule(
    "/src/modules/review/components/CustomsApproveDialog.tsx",
  );
  const html = renderToStaticMarkup(
    createElement(CustomsApproveDialog, {
      items: [{ id: 17, declarationNo: "TEST-17", status: "matched", statusLabel: "一致" }],
      onClose() {},
      onChanged() {},
    }),
  );
  assert.match(html, /cm-approve__note/);
  assert.match(html, /<label for="[^"]+">人工审核说明<\/label>/);
  assert.match(html, /选填，本次说明应用于全部选中回执/);
  assert.match(html, /<textarea[^>]*aria-describedby="[^"]+"[^>]*rows="3"/);
  assert.doesNotMatch(html, /<textarea[^>]*\brequired\b/);
  assert.match(html, /maxlength="300"/i);
  assert.match(html, /cm-approve__footer/);
  assert.match(html, /data-tone="success"/);
});

test("海关回执查询栏提供差异类型下拉，选项张数来自后端计数", async () => {
  const { CustomsSearchForm, EMPTY_CUSTOMS_SEARCH } = await server.ssrLoadModule(
    "/src/modules/review/components/CustomsSearchForm.tsx",
  );
  const counts = {
    receipts: 11,
    items: 23,
    matched: 6,
    splitMatched: 1,
    different: 2,
    nsMissing: 3,
    quantityMismatch: 1,
    unitMismatch: 0,
    totalMismatch: 2,
    lineMissing: 1,
  };
  const html = renderToStaticMarkup(
    createElement(CustomsSearchForm, {
      busy: false,
      counts,
      initial: { ...EMPTY_CUSTOMS_SEARCH, difference: "total_mismatch" },
      onSearch: () => {},
    }),
  );
  const select = html.slice(html.indexOf('<select name="difference"'), html.indexOf("</select>") + 9);
  const options = [...select.matchAll(/<option value="([^"]*)"( selected="")?>([^<]+)<\/option>/g)].map(
    (m) => [m[1], m[3], Boolean(m[2])],
  );
  assert.deepEqual(options, [
    ["", "全部类型", false],
    ["quantity_mismatch", "数量不一致（1 张）", false],
    ["unit_mismatch", "单位不一致（0 张）", false],
    ["total_mismatch", "总价不一致（2 张）", true],
    ["line_missing", "品名缺行（1 张）", false],
  ]);
  const { CustomsStats } = await server.ssrLoadModule("/src/modules/review/components/CustomsStats.tsx");
  const stats = renderToStaticMarkup(
    createElement(CustomsStats, { counts, value: "all", onSelect: () => {} }),
  );
  assert.equal((stats.match(/ui-stat__label/g) ?? []).length, 4);
  assert.match(stats, /有差异/);
});
