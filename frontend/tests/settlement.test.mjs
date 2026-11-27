import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { createServer } from "vite";

let server,
  navigation,
  subViewPath,
  ConsigneeSummary,
  LedgerGroupTable,
  LedgerSummaryTable,
  ReceivableStats,
  OverviewMetrics,
  OverviewCustomers,
  BankReceiptStats,
  CreateBatchDialog,
  createBatch;
// 含应用内链接的组件需要路由上下文。
const inRouter = (element) => createElement(MemoryRouter, null, element);

before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  ({ navigation } = await server.ssrLoadModule("/src/app/navigation.tsx"));
  ({ subViewPath } = await server.ssrLoadModule("/src/app/paths.ts"));
  ({ ConsigneeSummary } = await server.ssrLoadModule(
    "/src/modules/settlement/components/ConsigneeSummary.tsx",
  ));
  ({ LedgerGroupTable, LedgerSummaryTable } = await server.ssrLoadModule(
    "/src/modules/settlement/components/LedgerGroupTable.tsx",
  ));
  ({ ReceivableStats } = await server.ssrLoadModule(
    "/src/modules/settlement/components/ReceivableStats.tsx",
  ));
  ({ OverviewMetrics } = await server.ssrLoadModule(
    "/src/modules/settlement/components/OverviewMetrics.tsx",
  ));
  ({ OverviewCustomers } = await server.ssrLoadModule(
    "/src/modules/settlement/components/OverviewCustomers.tsx",
  ));
  ({ BankReceiptStats } = await server.ssrLoadModule(
    "/src/modules/settlement/components/BankReceiptStats.tsx",
  ));
  ({ CreateBatchDialog } = await server.ssrLoadModule(
    "/src/modules/settlement/components/CreateBatchDialog.tsx",
  ));
  ({ createBatch } = await server.ssrLoadModule("/src/modules/settlement/api.ts"));
});
after(() => server?.close());

test("回款登记保留原始金额字符串提交，由后端解释千分位", async (t) => {
  const body = {
    requestId: "d529d215-3d42-4ede-a23a-e1cf6af62b75",
    declarationNos: ["310120260514395336"],
    receivedOn: "2026-11-19",
    receivedAmount: "10,002.59",
    receivedFee: "0",
    payer: "Hongkong Yesop Connect Supply Limited",
    receivingAccount: "香港账户",
    receivedReference: "BANK-001",
    note: "",
  };
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "/api/settlement/batches");
    assert.deepEqual(JSON.parse(options.body), body);
    return Response.json({ id: 42 });
  });
  assert.deepEqual(await createBatch(body), { id: 42 });
  const html = renderToStaticMarkup(
    createElement(CreateBatchDialog, {
      declarationNos: body.declarationNos,
      defaultAmount: body.receivedAmount,
      onClose() {},
      onCreated() {},
    }),
  );
  assert.match(html, /value="10,002\.59"/);
  assert.match(html, /到账金额（必填）/);
  assert.match(html, /ui-button--primary[^>]*>登记并建批次/);
  assert.match(html, /<textarea[^>]*name="note"/);
});

test("结汇对账子菜单顺序：银行收汇明细在香港中转批次之前，直接收汇明细取代直接收汇批次", () => {
  const settlement = navigation.flatMap((group) => group.items).find((item) => item.id === "settlement");
  assert.deepEqual(
    settlement.children.map((child) => child.label),
    ["收汇总览", "报关应收汇", "银行收汇明细", "香港中转批次", "直接收汇明细", "合同抬头"],
  );
  assert.equal(subViewPath("settlement-overview"), "/settlement/overview");
  assert.equal(subViewPath("settlement-bank"), "/settlement/bank-receipts");
  assert.equal(subViewPath("settlement-direct"), "/settlement/direct");
});

test("收汇总览展示后端三项合计、路径拆分与负数超收，不自行重算", () => {
  const html = renderToStaticMarkup(
    createElement(OverviewMetrics, {
      total: {
        currency: "USD",
        declaredTotal: "1000.00",
        receivedTotal: "1005.10",
        outstanding: "-5.10",
        receivedFee: "2.00",
        routes: [
          {
            route: "hk_transit",
            routeLabel: "香港中转",
            declaredTotal: "600.00",
            receivedTotal: "600.00",
            outstanding: "0.00",
            receivedFee: "0.00",
          },
          {
            route: "direct",
            routeLabel: "直接收汇",
            declaredTotal: "400.00",
            receivedTotal: "405.10",
            outstanding: "-5.10",
            receivedFee: "2.00",
          },
        ],
      },
    }),
  );
  assert.match(html, /报关应收汇（总）/);
  assert.match(html, /实收汇金额（总）/);
  assert.match(html, /未收汇金额（总）/);
  assert.match(html, /1,005\.10/);
  assert.match(html, /-5\.10/);
  assert.match(html, /负数表示超收/);
  assert.match(html, /香港中转/);
  assert.match(html, /直接收汇/);
});

test("客户收汇明细按回款路径进入对应客户列表，不提供登记或结汇写操作", () => {
  const row = {
    consignee: "ACME & CO",
    currency: "USD",
    declarationCount: 1,
    declaredTotal: "600.00",
    receivedTotal: "585.00",
    outstanding: "15.00",
    receivedFee: "15.00",
  };
  const html = renderToStaticMarkup(
    inRouter(
      createElement(OverviewCustomers, {
        rows: [
          { ...row, route: "hk_transit", routeLabel: "香港中转" },
          { ...row, route: "direct", routeLabel: "直接收汇" },
        ],
      }),
    ),
  );
  assert.match(html, /href="\/settlement\/hk-transit\?consignee=ACME\+%26\+CO"/);
  assert.match(html, /href="\/settlement\/direct\?consignee=ACME\+%26\+CO"/);
  assert.match(html, /已登记手续费/);
  assert.doesNotMatch(html, /登记回款|确认结汇|确认资料已出/);
});

const customer = (overrides) => ({
  consignee: "ACME LTD",
  currency: "USD",
  route: "direct",
  routeLabel: "直接收汇",
  routeBasis: "境外收货人非集团香港公司",
  handling: "ledger",
  exportCompanies: ["上海毅烁"],
  count: 2,
  issueCount: 0,
  firstExportDate: "2026-10-13",
  lastExportDate: "2026-11-06",
  amount: "99200.00",
  receivedAmount: "12000.00",
  outstandingAmount: "87200.00",
  overpaidAmount: "0.00",
  receivedPercent: 12,
  receivedPercentText: "12%",
  stages: [
    { stage: "unpaid", label: "未收汇", count: 1 },
    { stage: "partial", label: "部分收汇", count: 1 },
  ],
  oldestAgingDays: 38,
  batchedCount: 0,
  pendingCount: 0,
  alertCount: 0,
  documentIssueCount: 0,
  documentNote: "留存 0/2 齐 · 不影响结汇",
  ...overrides,
});

test("按境外收货人汇总：展示后端已收、未收、阶段与资料，并按路径给出处理入口", () => {
  const drilled = [];
  const element = createElement(ConsigneeSummary, {
    rows: [
      customer({
        consignee: "HONGKONG VISION",
        route: "hk_transit",
        routeLabel: "香港中转",
        routeBasis: "境外收货人为集团香港公司",
        handling: "batch",
        count: 5,
        amount: "370150.00",
        receivedAmount: "256850.00",
        outstandingAmount: "113300.00",
        receivedPercent: 69,
        receivedPercentText: "69%",
        stages: [{ stage: "unregistered", label: "待登记回款", count: 2 }],
        batchedCount: 3,
        pendingCount: 2,
        alertCount: 1,
        issueCount: 1,
        documentIssueCount: 1,
        documentNote: "1 票资料未齐 · 2 票登记回款后办理",
      }),
      customer({ overpaidAmount: "5100.00" }),
    ],
    onDrill: (row) => drilled.push(row.consignee),
  });
  const html = renderToStaticMarkup(inRouter(element));
  assert.match(
    html,
    /href="\/settlement\/hk-transit\?tab=receipts&amp;consignee=HONGKONG\+VISION"[^>]*>去登记回款/,
  );
  assert.match(html, /已建批次 3 · 待登记 2/);
  assert.match(html, /1 票香港滞留超期/);
  assert.match(html, /1 张金额缺失未计入/);
  assert.match(html, /USD 370,150\.00/);
  assert.match(html, /aria-valuetext="69%"/);
  assert.match(html, /已登记到账 256,850\.00 · 未收 113,300\.00/);
  assert.match(html, /1 票待处理/);
  assert.match(html, /待登记回款 2/);
  assert.match(html, /href="\/settlement\/direct\?consignee=ACME\+LTD"[^>]*>客户总账/);
  assert.match(html, /推算已收 12,000\.00 · 未收 87,200\.00/);
  assert.match(html, /客户超收 5,100\.00/);
  assert.match(html, /留存 0\/2 齐 · 不影响结汇/);
  assert.match(html, /2026-10-13 至 2026-11-06/);
  assert.match(html, /未结汇最久 38 天/);
  assert.match(html, /看 5 票明细/);
});

const routeTotal = (route, overrides) => ({
  route,
  routeLabel: { all: "合计", hk_transit: "香港中转", direct: "直接收汇" }[route],
  currency: "USD",
  count: 0,
  amount: "0.00",
  receivedAmount: "0.00",
  outstandingAmount: "0.00",
  overpaidAmount: "0.00",
  pendingCount: 0,
  pendingAmount: "0.00",
  ...overrides,
});

test("应收汇概况只展示后端合计：总应收、两条路径、待登记回款与直接收汇待收", () => {
  const html = renderToStaticMarkup(
    createElement(ReceivableStats, {
      totals: [
        routeTotal("all", {
          count: 13,
          amount: "715450.00",
          receivedAmount: "496350.00",
          outstandingAmount: "219100.00",
        }),
        routeTotal("hk_transit", {
          count: 5,
          amount: "370150.00",
          receivedAmount: "256850.00",
          pendingCount: 2,
          pendingAmount: "113300.00",
        }),
        routeTotal("direct", {
          count: 8,
          amount: "345300.00",
          receivedAmount: "239500.00",
          outstandingAmount: "105800.00",
          overpaidAmount: "5100.00",
        }),
      ],
    }),
  );
  assert.match(html, /报关应收汇（总）（USD）[\s\S]*715,450\.00[\s\S]*13 票 · 未收 219,100\.00/);
  assert.match(html, /香港中转应收汇（USD）[\s\S]*370,150\.00[\s\S]*已到账 256,850\.00/);
  assert.match(html, /直接收汇应收汇（USD）[\s\S]*345,300\.00[\s\S]*已收 239,500\.00（推算）/);
  assert.match(html, /香港中转待登记回款（USD）[\s\S]*113,300\.00[\s\S]*2 票尚未建批次/);
  assert.match(html, /直接收汇待收金额（USD）[\s\S]*105,800\.00[\s\S]*另有超收 5,100\.00/);
  assert.equal(renderToStaticMarkup(createElement(ReceivableStats, { totals: [] })), "");
});

test("银行收汇按三个收款抬头出卡片，零金额不省略，其他抬头单独展示", () => {
  const names = ["上海绎色数码科技有限公司", "上海绎视数码科技有限公司", "上海毅鑫实业有限公司"];
  const base = { currency: "USD", count: 0, amount: "0.00", thirdPartyCount: 0, thirdPartyAmount: "0.00" };
  const html = renderToStaticMarkup(
    createElement(BankReceiptStats, {
      totals: [
        ...names.map((receivingCompany, index) => ({
          ...base,
          receivingCompany,
          featuredCompany: true,
          ...(index === 2
            ? { count: 2, amount: "1069499.39", thirdPartyCount: 1, thirdPartyAmount: "300.00" }
            : {}),
        })),
        { ...base, receivingCompany: "其他公司", featuredCompany: false, amount: "100.00", count: 1 },
      ],
    }),
  );
  for (const name of names) assert.match(html, new RegExp(name));
  assert.match(html, /USD · 2 笔/);
  assert.equal((html.match(/class="ui-stat"/g) || []).length, 3);
  assert.match(html, /1,069,499\.39/);
  assert.match(html, /当前条件下暂无收汇记录/);
  assert.match(html, /其他收款抬头/);
  assert.match(html, /其他公司：USD 100\.00/);
});

test("直接收汇明细末列显示各笔累计余额，保留来源单据", () => {
  const entry = (overrides) => ({
    kind: "export",
    kindLabel: "出口",
    exportCompany: "",
    exportDate: "",
    exportAmount: "",
    receiptCompany: "",
    receiptDate: "",
    receiptAmount: "",
    sourceNo: "",
    thirdParty: false,
    payerName: "",
    ...overrides,
  });
  const html = renderToStaticMarkup(
    inRouter(
      createElement(LedgerGroupTable, {
        group: {
          consignee: "ACME LTD",
          currency: "USD",
          exportTotal: "56900.00",
          receiptTotal: "62000.00",
          balance: "-5100.00",
          status: "overpaid",
          statusLabel: "超收",
          entries: [
            entry({
              exportCompany: "上海毅烁",
              exportDate: "2026-10-13",
              exportAmount: "56900.00",
              sourceNo: "223120260002291375",
              balance: "56900.00",
            }),
            entry({
              kind: "receipt",
              kindLabel: "收汇",
              receiptCompany: "上海毅烁",
              receiptDate: "2026-10-27",
              receiptAmount: "62000.00",
              sourceNo: "FT2610270009871",
              balance: "-5100.00",
              thirdParty: true,
              payerName: "HANSA PAY SERVICES LTD",
            }),
          ],
        },
      }),
    ),
  );
  for (const header of [
    "事务类型",
    "出口抬头",
    "出口日期",
    "出口金额",
    "收汇抬头",
    "实际到账日期",
    "收汇金额",
    "真实报关单号 / 银行流水号",
    "余额",
  ]) {
    assert.match(html, new RegExp(`<th[^>]*>${header}</th>`));
  }
  assert.match(html, /class="settlement-cell">223120260002291375<\/div>/);
  assert.match(
    html,
    /class="settlement-cell">FT2610270009871<span>三方代付 · 付款人 HANSA PAY SERVICES LTD<\/span>/,
  );
  // 出口行的收汇金额单元格留空，不显示占位符或 0
  const exportRow = html.slice(html.indexOf("<tbody>"), html.indexOf("</tr>", html.indexOf("<tbody>")));
  assert.equal((exportRow.match(/<td[^>]*><\/td>/g) ?? []).length, 3);
  assert.match(html, /<th[^>]*>资料<\/th><\/tr><\/thead>/);
  assert.match(exportRow, /<strong>56,900\.00<\/strong><\/td>/);
  assert.match(exportRow, /tab=documents&amp;consignee=ACME\+LTD&amp;declarationNo=223120260002291375/);
  assert.match(html, /<strong>-5,100\.00<\/strong><\/td><td>—<\/td><\/tr>/);
  assert.doesNotMatch(html, /协议|待匹配金额|收汇匹配|期末余额/);
});

test("直接收汇默认按收货人和币种显示汇总，逐笔流水默认收起", () => {
  const group = {
    consignee: "ACME LTD",
    currency: "USD",
    receivingCompany: "上海毅烁",
    openingBalance: "1000.00",
    exportTotal: "56900.00",
    receiptTotal: "62000.00",
    balance: "-5100.00",
    status: "overpaid",
    statusLabel: "超收",
    entries: [{ sourceNo: "FT2610270009871" }],
  };
  const html = renderToStaticMarkup(
    inRouter(createElement(LedgerSummaryTable, { groups: [group, { ...group, currency: "EUR" }] })),
  );
  for (const title of [
    "境外收货人",
    "收款人（收汇抬头）",
    "状态",
    "期初差额",
    "本期出口",
    "本期收汇",
    "期末差额",
  ]) {
    assert.match(html, new RegExp(`<th[^>]*>${title}</th>`));
  }
  assert.match(html, /aria-expanded="false" aria-label="展开 ACME LTD USD 的流水"/);
  assert.match(html, /aria-expanded="false" aria-label="展开 ACME LTD EUR 的流水"/);
  assert.doesNotMatch(html, /settlement-ledger__meta">USD<\/div>/);
  assert.match(
    html,
    /settlement-ledger__meta">EUR<\/div><\/td><td>上海毅烁<\/td><td><span class="ui-badge"[^>]*>超收/,
  );
  assert.match(html, /56,900\.00[\s\S]*62,000\.00[\s\S]*-5,100\.00/);
  assert.doesNotMatch(html, /FT2610270009871|ui-table__details|事务类型/);
});

test("收汇路径表展示后端全量汇总、独立币种及带客户筛选的查看入口", async () => {
  const { OverviewRoutes } = await server.ssrLoadModule(
    "/src/modules/settlement/components/OverviewRoutes.tsx",
  );
  const amounts = {
    declaredTotal: "9000000000000.01",
    receivedTotal: "100.00",
    outstanding: "-8.88",
    receivedFee: "3.00",
  };
  const html = renderToStaticMarkup(
    inRouter(
      createElement(OverviewRoutes, {
        consignee: "ACME & CO",
        totals: [
          {
            ...amounts,
            currency: "USD",
            routes: [
              { ...amounts, route: "hk_transit", routeLabel: "香港中转" },
              { ...amounts, route: "direct", routeLabel: "直接收汇" },
            ],
          },
          {
            ...amounts,
            currency: "EUR",
            routes: [{ ...amounts, route: "direct", routeLabel: "直接收汇" }],
          },
        ],
      }),
    ),
  );
  assert.match(html, /按收汇路径查看/);
  assert.match(html, /9,000,000,000,000\.01/);
  assert.match(html, /-8\.88/);
  assert.match(html, /USD/);
  assert.match(html, /EUR/);
  assert.match(html, /香港汇回境内不再次增加实收汇金额/);
  assert.match(html, /href="\/settlement\/hk-transit\?consignee=ACME\+%26\+CO"/);
  assert.match(html, /href="\/settlement\/direct\?consignee=ACME\+%26\+CO"/);
});

test("报关应收汇默认按客户汇总，报关单明细位于右侧并共用一个查询区", async () => {
  const { ReceivablePanel } = await server.ssrLoadModule(
    "/src/modules/settlement/components/ReceivablePanel.tsx",
  );
  const html = renderToStaticMarkup(inRouter(createElement(ReceivablePanel)));
  assert.match(html, /aria-label="报关应收汇展示方式"/);
  assert.match(html, /aria-pressed="true">按客户汇总<\/button><button[^>]*aria-pressed="false">报关单明细/);
  assert.equal((html.match(/<form/g) || []).length, 1);
  assert.equal((html.match(/class="ui-card /g) || []).length, 1);
  assert.match(html, /正在汇总客户应收汇/);
  assert.doesNotMatch(html, /正在读取报关单明细/);
});

test("报关明细视图与已提交筛选可从地址恢复，非法展示方式回到客户汇总", async () => {
  const { ReceivablePanel } = await server.ssrLoadModule(
    "/src/modules/settlement/components/ReceivablePanel.tsx",
  );
  const render = (entry) =>
    renderToStaticMarkup(
      createElement(MemoryRouter, { initialEntries: [entry] }, createElement(ReceivablePanel)),
    );
  const html = render(
    "/settlement?view=declarations&consignee=HK+%26+CO&declarationNo=31012026&route=hk_transit&stage=remit&exportFrom=2026-11-01&exportTo=2026-11-19",
  );
  assert.match(html, /aria-pressed="false">按客户汇总<\/button><button[^>]*aria-pressed="true">报关单明细/);
  assert.match(html, /name="consignee"[^>]*value="HK &amp; CO"/);
  assert.match(html, /name="declarationNo"[^>]*value="31012026"/);
  assert.match(html, /option value="hk_transit" selected=""/);
  assert.match(html, /name="exportFrom"[^>]*value="2026-11-01"/);
  assert.match(html, /name="exportTo"[^>]*value="2026-11-19"/);
  assert.match(html, /正在读取报关单明细/);
  const fallback = render("/settlement?view=unknown&route=unknown&stage=unknown");
  assert.match(fallback, /aria-pressed="true">按客户汇总/);
  assert.match(fallback, /option value="all" selected=""/);
});

test("报关应收页不再登记回款；香港待登记页提供勾选与登记入口", async () => {
  const { ReceivablePanel } = await server.ssrLoadModule(
    "/src/modules/settlement/components/ReceivablePanel.tsx",
  );
  const { SettlementHkTransitPage } = await server.ssrLoadModule(
    "/src/modules/settlement/pages/SettlementHkTransitPage.tsx",
  );
  const browse = renderToStaticMarkup(inRouter(createElement(ReceivablePanel)));
  assert.doesNotMatch(browse, /登记回款并建批次|name="targetAmount"/);
  assert.match(browse, /进入香港中转登记/);
  assert.match(browse, /tab=receipts/);
  const registration = renderToStaticMarkup(
    createElement(
      MemoryRouter,
      {
        initialEntries: ["/settlement/hk-transit?tab=receipts&consignee=HK"],
      },
      createElement(SettlementHkTransitPage),
    ),
  );
  assert.match(registration, /待登记香港回款/);
  assert.match(registration, /全部批次/);
  assert.match(registration, /正在读取香港中转工作区/);
  assert.match(registration, /name="keyword"/);
  assert.match(registration, /香港中转查看范围/);
  assert.match(registration, /value="HK"/);
  assert.doesNotMatch(registration, /name="route"/);
  assert.doesNotMatch(registration, /报关应收汇展示方式|按客户汇总/);
});

const receivable = (overrides) => ({
  declarationNo: "REAL1",
  recordNo: "CD1",
  consignee: "HK & CO",
  exportCompany: "上海毅鑫实业有限公司",
  exportDate: "2026-10-15",
  salesOrders: ["SO1"],
  currency: "USD",
  amount: "118300.00",
  route: "hk_transit",
  routeLabel: "香港中转",
  routeBasis: "境外收货人为集团香港公司",
  receivedAmount: "118300.00",
  outstandingAmount: "0.00",
  receivedBasis: "已登记香港到账（到账 + 手续费）",
  receivedPercent: 100,
  receivedPercentText: "100%",
  stage: "collected",
  stageLabel: "香港已收·办资料",
  agingDays: 35,
  alert: "",
  issue: "",
  batchId: 12,
  batchNo: "SB20261110-00012",
  documentStatus: "pending",
  documentLabel: "资料未齐",
  documentNote: "出口合同号 YX-034 未生成合同",
  ...overrides,
});

test("报关单明细逐单显示后端收款、资料、结汇状态，并指向所在批次或客户总账", async () => {
  const { ReceivableTable } = await server.ssrLoadModule(
    "/src/modules/settlement/components/ReceivableTable.tsx",
  );
  const html = renderToStaticMarkup(
    inRouter(
      createElement(ReceivableTable, {
        rows: [
          receivable(),
          receivable({
            declarationNo: "REAL2",
            stage: "remit",
            stageLabel: "资料已出·待汇回",
            alert: "香港滞留 40 天",
            documentStatus: "ready",
            documentLabel: "资料已出",
            documentNote: "",
          }),
          receivable({
            declarationNo: "REAL3",
            batchId: null,
            batchNo: "",
            stage: "unregistered",
            stageLabel: "待登记回款",
            receivedAmount: "0.00",
            outstandingAmount: "64800.00",
            receivedPercent: 0,
            receivedPercentText: "0%",
            documentStatus: "after_batch",
            documentLabel: "登记回款后办理",
            documentNote: "",
          }),
          receivable({
            declarationNo: "DIRECT1",
            consignee: "SAKURA",
            route: "direct",
            routeLabel: "直接收汇",
            batchId: null,
            batchNo: "",
            stage: "partial",
            stageLabel: "部分收汇",
            receivedAmount: "8800.00",
            outstandingAmount: "18600.00",
            receivedPercent: 32,
            receivedPercentText: "32%",
            documentStatus: "none",
            documentLabel: "未办理",
            documentNote: "",
          }),
        ],
      }),
    ),
  );
  assert.match(html, /href="\/settlement\/hk-transit\/batches\/12"[^>]*>去批次办资料/);
  assert.match(html, /href="\/settlement\/hk-transit\/batches\/12\?mode=remit"[^>]*>去批次登记汇回</);
  assert.match(html, /香港滞留 40 天/);
  assert.match(html, /出口合同号 YX-034 未生成合同/);
  assert.match(
    html,
    /href="\/settlement\/hk-transit\?tab=receipts&amp;consignee=HK\+%26\+CO"[^>]*>去登记回款/,
  );
  assert.match(html, /推算已收 8,800\.00 · 未收 18,600\.00/);
  assert.match(html, /href="\/settlement\/direct\?consignee=SAKURA"[^>]*>客户总账/);
  assert.match(
    html,
    /href="\/settlement\/direct\?tab=documents&amp;consignee=SAKURA&amp;declarationNo=DIRECT1"/,
  );
  assert.match(html, /aria-valuetext="32%"/);
  assert.match(html, /35 天/);
});

test("待登记回款只允许勾选香港中转报关单，并保留后端不可选原因", async () => {
  const { CandidateTable } = await server.ssrLoadModule(
    "/src/modules/settlement/components/CandidateTable.tsx",
  );
  const hk = {
    declarationNo: "REAL1",
    recordNo: "CD1",
    salesOrders: ["SO1"],
    consignee: "HK & CO",
    exportDate: "2026-11-01",
    route: "hk_transit",
    routeLabel: "香港中转",
    routeBasis: "香港公司",
    handling: "batch",
    amount: "100.00",
    currency: "USD",
    blockedReason: "",
    batchNo: "",
  };
  const rows = [
    hk,
    { ...hk, declarationNo: "REAL2", blockedReason: "已在有效批次中" },
    { ...hk, declarationNo: "DIRECT1", route: "direct", routeLabel: "直接收汇", handling: "ledger" },
  ];
  const registration = renderToStaticMarkup(
    inRouter(
      createElement(CandidateTable, {
        rows,
        selection: { selected: ["REAL1"], onToggle: () => undefined },
      }),
    ),
  );
  assert.equal((registration.match(/type="checkbox"/g) || []).length, 2);
  assert.match(registration, /选择报关单 REAL2[^>]*disabled/);
  assert.match(registration, /已在有效批次中/);
  assert.match(registration, /可登记回款/);
});

test("直接收汇保留客户总账，旧单票 URL 经自动建组入口定位资料组", async () => {
  const { SettlementLedgerPage } = await server.ssrLoadModule(
    "/src/modules/settlement/pages/SettlementLedgerPage.tsx",
  );
  function renderAt(url) {
    return renderToStaticMarkup(
      createElement(MemoryRouter, { initialEntries: [url] }, createElement(SettlementLedgerPage)),
    );
  }
  const ledger = renderAt("/settlement/direct");
  assert.match(ledger, /客户总账/);
  assert.match(ledger, /报关资料/);
  assert.match(ledger, /正在读取直接收汇明细/);
  const docs = renderAt("/settlement/direct?tab=documents&consignee=ACME&declarationNo=REAL872");
  assert.match(docs, /正在打开单票资料组/);
  assert.match(docs, /value="ACME"/);
  assert.doesNotMatch(docs, /办理资料 · REAL872/);
  const singles = renderAt("/settlement/direct?tab=documents&consignee=ACME");
  assert.match(singles, /报关资料 · 一票一组/);
  assert.match(singles, /当前客户范围：ACME/);
  assert.doesNotMatch(docs, /登记回款并建批次|name="receivedAmount"/);
});

test("合同双方按报关依据只读展示，不提供手选卖方", async () => {
  const { ContractGenerateForm } = await server.ssrLoadModule(
    "/src/modules/settlement/components/ContractGenerateForm.tsx",
  );
  const html = renderToStaticMarkup(
    inRouter(
      createElement(ContractGenerateForm, {
        documents: {
          defaults: {
            sellerPartyId: 2,
            tradeTerm: "FOB",
            paymentTermsCn: "预付",
            paymentTermsEn: "In advance",
          },
          planned: [
            {
              contractNo: "CONTRACT-1",
              declarationNos: ["REAL872"],
              buyerName: "境外客户 A",
              sellerName: "NS 申报公司 B",
            },
          ],
          sellers: [{ id: 9, name: "无关公司" }],
        },
        busy: false,
        onCancel: () => undefined,
        onSubmit: () => undefined,
      }),
    ),
  );
  assert.match(html, /买方（境外收货人）/);
  assert.match(html, /卖方（NS 申报抬头）/);
  assert.match(html, /境外客户 A/);
  assert.match(html, /NS 申报公司 B/);
  assert.match(html, /REAL872/);
  assert.doesNotMatch(html, /name="sellerPartyId"|无关公司|请选择/);
});

test("香港中转待登记面板使用后端许可、显示分页与选择数量", async () => {
  const { HkPendingPanel } = await server.ssrLoadModule(
    "/src/modules/settlement/components/HkPendingPanel.tsx",
  );
  const row = {
    declarationNo: "TEST-HK-001",
    recordNo: "CD1",
    consignee: "TEST HK LTD",
    exportCompany: "测试抬头",
    currency: "USD",
    amount: "1234.50",
    exportDate: "2026-11-01",
    waitingLabel: "出口 19 天",
    select: { allowed: true, reason: "" },
  };
  const html = renderToStaticMarkup(
    inRouter(
      createElement(HkPendingPanel, {
        rows: [row, { ...row, declarationNo: "BLOCKED", select: { allowed: false, reason: "金额待补" } }],
        total: 2,
        page: 1,
        pageCount: 1,
        pageSize: 20,
        selected: [row.declarationNo],
        onToggle() {},
        onToggleAll() {},
        onPageChange() {},
        onPageSizeChange() {},
        onRegister() {},
      }),
    ),
  );
  assert.match(html, /登记回款（1 票）/);
  assert.match(html, /1,234.50/);
  assert.match(html, /选择报关单 BLOCKED[^>]*disabled/);
  assert.match(html, /金额待补/);
  assert.match(html, /出口 19 天/);
});

test("香港批次卡展示真实流程摘要与资料包许可", async () => {
  const { HkBatchCard } = await server.ssrLoadModule("/src/modules/settlement/components/HkBatchCard.tsx");
  const row = {
    batch: {
      id: 8,
      batchNo: "TEST-BATCH-008",
      status: "settled",
      statusLabel: "已结汇",
      consignee: "TEST HK",
      currency: "USD",
      declaredTotal: "1200.00",
      receivedOn: "2026-11-01",
      receivedAmount: "1190.00",
      receivedFee: "10.00",
      receivedReference: "REF-1",
      declarationCount: 2,
      actions: { settle: { allowed: false, reason: "已结汇" } },
    },
    waitingLabel: "2026-11-05 结汇",
    overdue: false,
    issue: "",
    notice: "",
    documents: [{ label: "提单", ready: true, description: "已齐全" }],
    steps: [
      { key: "received", label: "香港到账", description: "2026-11-01", state: "done" },
      { key: "documents", label: "资料齐全", description: "已齐全", state: "done" },
      { key: "sent", label: "资料已出", description: "已确认", state: "done" },
      { key: "settled", label: "汇回结汇", description: "已结汇", state: "done" },
    ],
    primaryAction: "package",
    primaryLabel: "下载资料包",
    package: { allowed: true, reason: "" },
    packageUrl: "/api/settlement/batches/8/package",
  };
  const html = renderToStaticMarkup(inRouter(createElement(HkBatchCard, { row })));
  assert.match(html, /TEST-BATCH-008/);
  assert.match(html, /1,200.00/);
  assert.match(html, /href="\/api\/settlement\/batches\/8\/package" download/);
  assert.match(html, /aria-expanded="true"[^>]*>收起流程/);
  assert.match(html, /批次 TEST-BATCH-008 处理流程/);
  assert.match(html, /香港到账/);
  assert.match(html, /汇回结汇/);
  assert.doesNotMatch(html, /展开资料|收起资料/);
  const documents = renderToStaticMarkup(
    inRouter(
      createElement(HkBatchCard, {
        row: { ...row, primaryAction: "documents", primaryLabel: "办理资料" },
      }),
    ),
  );
  assert.match(documents, /href="\/settlement\/hk-transit\/batches\/8"[^>]*>办理资料/);
  assert.doesNotMatch(documents, /展开资料|收起资料/);
  assert.doesNotMatch(html, /正在读取批次|批次报关单|结汇资料读取失败/);
  const blocked = renderToStaticMarkup(
    inRouter(
      createElement(HkBatchCard, {
        row: { ...row, package: { allowed: false, reason: "资料待补" } },
      }),
    ),
  );
  assert.doesNotMatch(blocked, /href="\/api\/settlement\/batches\/8\/package"/);
  assert.match(blocked, /disabled="" title="资料待补"/);
});

test("香港批次登记汇回入口沿用后端许可", async () => {
  const { HkBatchCard } = await server.ssrLoadModule("/src/modules/settlement/components/HkBatchCard.tsx");
  const row = {
    batch: {
      id: 9,
      batchNo: "TEST-009",
      status: "documents_ready",
      statusLabel: "资料已出",
      consignee: "TEST HK",
      currency: "USD",
      declaredTotal: "100.00",
      receivedOn: "2026-11-01",
      receivedAmount: "100.00",
      receivedFee: "0.00",
      receivedReference: "REF-9",
      declarationCount: 1,
      actions: { settle: { allowed: false, reason: "后端核对未通过" } },
    },
    waitingLabel: "滞留香港 3 天",
    overdue: false,
    issue: "",
    notice: "",
    documents: [],
    steps: [],
    primaryAction: "remit",
    primaryLabel: "登记汇回",
    package: { allowed: false, reason: "资料待补" },
    packageUrl: "",
  };
  const html = renderToStaticMarkup(inRouter(createElement(HkBatchCard, { row })));
  assert.match(html, /disabled="" title="后端核对未通过"[^>]*>登记汇回/);
  const allowed = renderToStaticMarkup(
    inRouter(
      createElement(HkBatchCard, {
        row: { ...row, batch: { ...row.batch, actions: { settle: { allowed: true, reason: "" } } } },
      }),
    ),
  );
  assert.match(allowed, /href="\/settlement\/hk-transit\/batches\/9\?mode=remit"[^>]*>登记汇回/);
  assert.doesNotMatch(allowed, /<form|正在读取批次/);
});

test("香港批次资料地址可直达，列表入口保留导航语义", async () => {
  const { paths, settlementHkBatchPath } = await server.ssrLoadModule("/src/app/paths.ts");
  assert.equal(settlementHkBatchPath(12), `${paths.settlementHkBatches}/12`);
  assert.equal(settlementHkBatchPath(12, true), `${paths.settlementHkBatches}/12?mode=remit`);
  const { SettlementHkBatchPage } = await server.ssrLoadModule(
    "/src/modules/settlement/pages/SettlementHkBatchPage.tsx",
  );
  const html = renderToStaticMarkup(inRouter(createElement(SettlementHkBatchPage, { batchId: 12 })));
  assert.match(html, /正在读取批次/);
  assert.doesNotMatch(html, /香港中转处理阶段|当前条件下没有/);
});

test("香港批次概览使用真实金额与后端票数，不展示已删除的信息页签", async () => {
  const { BatchOverview } = await server.ssrLoadModule(
    "/src/modules/settlement/components/BatchOverview.tsx",
  );
  const html = renderToStaticMarkup(
    createElement(BatchOverview, {
      batch: {
        batchNo: "SB-REAL-12",
        route: "hk_transit",
        routeLabel: "香港中转",
        status: "collected",
        statusLabel: "香港已收",
        consignee: "REAL HK LTD",
        currency: "EUR",
        declaredTotal: "1234.56",
        receivedOn: "2026-11-27",
        receivedAmount: "1230.56",
        receivedFee: "4.00",
        declarationCount: 7,
        receivedReference: "REF-REAL",
        receivedSlipUrl: "/api/slip/12",
        receivedSlipName: "银行水单.pdf",
        items: [],
      },
    }),
  );
  assert.match(html, /1,234\.56/);
  assert.match(html, /EUR 1,230\.56 \/ 4\.00/);
  assert.match(html, /7 张/);
  assert.match(html, /href="\/api\/slip\/12"/);
  assert.doesNotMatch(html, /批次信息|批次报关单|HTML 示例/);
});

test("汇回表单沿用后端许可、保留真实已登记金额与手续费提醒", async () => {
  const { BatchRemittanceForm } = await server.ssrLoadModule(
    "/src/modules/settlement/components/BatchRemittanceForm.tsx",
  );
  const batch = {
    currency: "USD",
    status: "documents_ready",
    statusLabel: "资料已出",
    remittedOn: "",
    balances: [],
    actions: { settle: { allowed: false, reason: "请先补齐合同" } },
  };
  const props = { batch, busy: false, onSubmit() {}, onCancel() {} };
  const blocked = renderToStaticMarkup(createElement(BatchRemittanceForm, props));
  assert.match(blocked, /请先补齐合同/);
  assert.match(blocked, /<input(?=[^>]*name="remittedAmount")(?=[^>]*disabled)[^>]*>/);
  assert.match(blocked, /<button(?=[^>]*type="submit")(?=[^>]*disabled)[^>]*>/);
  const enabled = renderToStaticMarkup(
    createElement(BatchRemittanceForm, {
      ...props,
      batch: { ...batch, actions: { settle: { allowed: true, reason: "" } } },
    }),
  );
  assert.doesNotMatch(enabled, /disabled/);
  const saved = renderToStaticMarkup(
    createElement(BatchRemittanceForm, {
      ...props,
      batch: {
        ...batch,
        status: "settled",
        statusLabel: "已结汇",
        remittedOn: "2026-11-27",
        remittedAmount: "1200.01",
        remittedFee: "34.55",
        remittedReference: "BANK-REAL",
        settledBy: "财务甲",
        actions: { settle: { allowed: false, reason: "已结汇" } },
        balances: [{ stage: "remitted", label: "汇回", balanced: true, warnings: ["手续费需复核"] }],
      },
    }),
  );
  assert.match(saved, /1,200\.01/);
  assert.match(saved, /34\.55/);
  assert.match(saved, /手续费需复核/);
  assert.doesNotMatch(saved, /<form/);
});

test("汇回请求保留十进制字符串且失败不自动重试", async (t) => {
  const { recordRemittance } = await server.ssrLoadModule("/src/modules/settlement/api.ts");
  const body = {
    remittedOn: "2026-11-27",
    remittedAmount: "1,200.0100",
    remittedFee: "0.0001",
    remittedReference: "BANK-12",
  };
  let calls = 0;
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls += 1;
    assert.equal(url, "/api/settlement/batches/12/remittance");
    assert.deepEqual(JSON.parse(options.body), body);
    return Response.json({ error: "汇回金额未对平" }, { status: 409 });
  });
  await assert.rejects(recordRemittance(12, body), /汇回金额未对平/);
  assert.equal(calls, 1);
});

test("报关单详情地址保留列表筛选并支持特殊字符编号", async () => {
  const { settlementDeclarationDetailPath } = await server.ssrLoadModule("/src/app/paths.ts");
  const url = settlementDeclarationDetailPath(
    "TEST/001 中文",
    "/settlement",
    "?view=declarations&route=direct&consignee=ACME",
  );
  const params = new URLSearchParams(url.split("?")[1]);
  assert.equal(params.get("detail"), "TEST/001 中文");
  assert.equal(params.get("route"), "direct");
  assert.equal(params.get("consignee"), "ACME");
});

test("报关单结汇详情显示后端冲抵、三方付款人及只读资料", async () => {
  const { DeclarationDetailBody } = await server.ssrLoadModule(
    "/src/modules/settlement/components/DeclarationDetailBody.tsx",
  );
  const detail = {
    item: receivable({
      route: "direct",
      routeLabel: "直接收汇",
      declarationNo: "DIRECT-002",
      stage: "partial",
      stageLabel: "部分收汇",
      currency: "USD",
      exportCompany: "测试抬头",
      exportDate: "2026-11-10",
      agingDays: 10,
    }),
    steps: [
      { key: "export", label: "报关", description: "2026-11-10", state: "done", percent: 100 },
      {
        key: "receipt",
        label: "收汇 57%",
        description: "已收 5,000.00 · 未收 3,750.00",
        state: "current",
        percent: 57,
      },
    ],
    batch: null,
    allocations: [
      {
        declarationNo: "DIRECT-002",
        exportDate: "2026-11-10",
        amount: "8750.00",
        receivedAmount: "5000.00",
        outstandingAmount: "3750.00",
        current: true,
        receipts: [
          {
            receiptId: 2,
            date: "2026-11-15",
            reference: "FT-SOURCE",
            receiptAmount: "17500.00",
            appliedAmount: "5000.00",
            payer: "PAYING AGENT LTD",
            thirdParty: true,
          },
        ],
      },
    ],
    ledgerBalance: "3750.00",
    ledgerNote: "先出口先冲抵，不保存人工分配关系。",
    documents: {
      scopeKind: "single",
      scopeLabel: "本报关单资料",
      scopeNumbers: ["DIRECT-002"],
      note: "按单票留存，不影响结汇",
      original: {
        statusLabel: "已归档",
        archived: true,
        files: [{ name: "报关单.xls", url: "/api/settlement/receivables/DIRECT-002/originals/0" }],
        note: "",
      },
      bills: [],
      contracts: [],
      issues: ["本单缺提单"],
      warnings: ["提醒而非阻断"],
    },
    events: [],
    asOf: "2026-11-20",
  };
  const html = renderToStaticMarkup(inRouter(createElement(DeclarationDetailBody, { detail })));
  assert.match(html, /FT-SOURCE/);
  assert.match(html, /本单冲抵 5,000.00/);
  assert.match(html, /三方代付 · 付款人 PAYING AGENT LTD/);
  assert.match(html, /data-tone="accent"/);
  assert.match(html, /需要处理的资料缺项（1 项）/);
  assert.match(html, /资料包提醒/);
  assert.match(html, /去办理本单资料/);
  assert.match(html, /originals\/0/);
  assert.doesNotMatch(html, /上传提单 PDF|按模板生成|确认已结汇|合并办理资料/);
});

test("结汇详情入口使用当前页面地址，打开侧栏不清除查询", async () => {
  const { DeclarationDetailLink } = await server.ssrLoadModule(
    "/src/modules/settlement/components/DeclarationDetailLink.tsx",
  );
  const html = renderToStaticMarkup(
    createElement(
      MemoryRouter,
      { initialEntries: ["/settlement/hk-transit?stage=collected&page=2"] },
      createElement(DeclarationDetailLink, { number: "HK-001" }),
    ),
  );
  assert.match(html, /stage=collected&amp;page=2&amp;detail=HK-001/);
  assert.match(html, /查看报关单 HK-001 结汇详情/);
});

test("结汇进度按路径显示阶段金额、共用刻度和后端比例", async () => {
  const { SettlementProgressChart } = await server.ssrLoadModule(
    "/src/modules/settlement/components/SettlementProgressChart.tsx",
  );
  const stage = {
    key: "partial",
    label: "部分收汇",
    count: 2,
    amount: "84300.00",
    receivedAmount: "20800.00",
    outstandingAmount: "63500.00",
    barWidth: "37.25",
    tone: "progress",
    note: "其中已收 20,800.00 · 未收 63,500.00",
    select: { allowed: true, reason: "" },
  };
  const data = {
    currency: "USD",
    amount: "715450.00",
    count: 13,
    settledAmount: "305100.00",
    settledCount: 6,
    unsettledAmount: "410350.00",
    unsettledCount: 7,
    settledPercent: "42.64",
    settledPercentText: "42.6%",
    barMaximum: "200000.00",
    routes: [
      {
        route: "hk_transit",
        label: "香港中转",
        amount: "483750.00",
        count: 7,
        note: "汇回境内对平才结汇",
        stages: [
          {
            ...stage,
            key: "unregistered",
            label: "待登记回款",
            amount: "0.00",
            count: 0,
            barWidth: "0.00",
            select: { allowed: false, reason: "本阶段暂无报关单" },
          },
        ],
      },
      {
        route: "direct",
        label: "直接收汇",
        amount: "231700.00",
        count: 6,
        note: "收齐自动结汇",
        stages: [stage],
      },
    ],
  };
  const html = renderToStaticMarkup(
    inRouter(createElement(SettlementProgressChart, { data, consignee: "ACME LTD" })),
  );
  assert.match(html, /香港中转阶段金额/);
  assert.match(html, /直接收汇阶段金额/);
  assert.match(html, /84,300.00/);
  assert.match(html, /其中已收 20,800.00 · 未收 63,500.00/);
  assert.match(html, /width:37.25%/);
  assert.match(html, /42.6%/);
  assert.match(html, /阶段报关金额不等于未收金额/);
  assert.match(html, /stage=partial&amp;currency=USD&amp;consignee=ACME\+LTD/);
  assert.match(html, /aria-disabled="true"/);
  assert.doesNotMatch(html, /href="[^"]*stage=unregistered/);
});

test("香港回款独立页只人工填写流水，水单仅作为附件", async () => {
  const { HkReceiptFields } = await server.ssrLoadModule(
    "/src/modules/settlement/components/HkReceiptFields.tsx",
  );
  const html = renderToStaticMarkup(
    createElement(HkReceiptFields, {
      fields: {
        receivedOn: "2026-11-18",
        receivedAmount: "1,000.50",
        receivedFee: "0",
        payer: "手工付款方",
        receivingAccount: "",
        receivedReference: "MANUAL-001",
        note: "",
      },
      payer: "手工付款方",
      currency: "USD",
      accounts: [],
      busy: false,
      readingFile: false,
      errors: { receivedAmount: "请核对到账金额" },
      bankSlip: { fileName: "扫描水单.pdf", content: "base64" },
      onChange() {},
      onFile() {},
    }),
  );
  assert.match(html, /人工填写/);
  assert.doesNotMatch(html, /识别|自动填入|OCR/);
  assert.match(html, /<input(?=[^>]*name="receivedOn")(?=[^>]*type="date")[^>]*>/);
  assert.match(html, /value="1,000.50"/);
  assert.match(html, /aria-invalid="true"/);
  assert.match(html, /扫描水单.pdf · 已选择，提交时随批次保存/);
});

test("香港登记提交许可跟随后端，核对中、失败和未对平禁止提交", async () => {
  const { HkReceiptReconciliation } = await server.ssrLoadModule(
    "/src/modules/settlement/components/HkReceiptReconciliation.tsx",
  );
  const data = {
    currency: "USD",
    amount: "950.00",
    fee: "50.00",
    arrivedTotal: "1000.00",
    declaredTotal: "1000.00",
    difference: "0.00",
    balanced: true,
    rows: [{}],
    checks: [{ key: "fee", label: "手续费预警", detail: "超预警但可提交", state: "warning" }],
    submit: { allowed: true, reason: "" },
  };
  const render = (overrides = {}) =>
    renderToStaticMarkup(
      createElement(HkReceiptReconciliation, {
        data,
        loading: false,
        error: "",
        busy: false,
        formId: "register",
        onCancel() {},
        ...overrides,
      }),
    );
  assert.doesNotMatch(render(), /<button(?=[^>]*type="submit")(?=[^>]*disabled)[^>]*>/);
  assert.match(render(), /提醒/);
  for (const overrides of [
    { loading: true },
    { busy: true },
    { error: "网络错误" },
    { data: { ...data, submit: { allowed: false, reason: "差额未对平" } } },
  ]) {
    assert.match(render(overrides), /<button(?=[^>]*type="submit")(?=[^>]*disabled)[^>]*>/);
  }
  assert.match(render({ data: { ...data, submit: { allowed: false, reason: "差额未对平" } } }), /差额未对平/);
});

test("独立登记路径和人工金额、附件原文提交", async (t) => {
  const { settlementHkRegistrationPath } = await server.ssrLoadModule("/src/app/paths.ts");
  const target = new URL(settlementHkRegistrationPath(["CD001", "CD002"], "draft-01"), "http://localhost");
  assert.equal(target.pathname, "/settlement/hk-transit/register");
  assert.deepEqual(target.searchParams.getAll("declarationNo"), ["CD001", "CD002"]);
  assert.equal(target.searchParams.get("draft"), "draft-01");
  const { registerHkReceipt } = await server.ssrLoadModule("/src/modules/settlement/api/hk-receipt-api.ts");
  const body = {
    requestId: "draft-01",
    declarationNos: ["CD001"],
    receivedOn: "2026-11-18",
    receivedAmount: "1,000.50",
    receivedFee: "0",
    bankSlip: { fileName: "扫描件.pdf", content: "base64" },
  };
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "/api/settlement/hk-workbench/register");
    assert.deepEqual(JSON.parse(options.body), body);
    return Response.json({ id: 42 });
  });
  assert.deepEqual(await registerHkReceipt(body), { id: 42 });
});

test("总览账龄、真实待办入口及超过 100% 的收款进度直接展示后端数据", async () => {
  const { OverviewInsights } = await server.ssrLoadModule(
    "/src/modules/settlement/components/OverviewInsights.tsx",
  );
  const html = renderToStaticMarkup(
    inRouter(
      createElement(OverviewInsights, {
        asOf: "2026-11-20",
        data: {
          currency: "USD",
          unsettledAmount: "410350.00",
          unsettledCount: 7,
          unknownDateCount: 1,
          aging: [{ label: "0–30 天", amount: "183000.00", count: 4, barWidth: "80.49", tone: "info" }],
          actions: [
            {
              key: "register",
              title: "登记香港回款",
              description: "2 票未登记到账",
              amount: "113300.00",
              tone: "warning",
              target: "receipts",
              route: "all",
              stage: "all",
              consignee: "ACME & CO",
              batchNo: "",
            },
          ],
        },
      }),
    ),
  );
  assert.match(html, /未结汇账龄/);
  assert.match(html, /410,350\.00/);
  assert.match(html, /width:80\.49%/);
  assert.match(html, /未计入账龄分段/);
  assert.match(html, /\/settlement\/hk-transit\?consignee=ACME\+%26\+CO&amp;currency=USD&amp;tab=receipts/);
  const customers = renderToStaticMarkup(
    inRouter(
      createElement(OverviewCustomers, {
        rows: [
          {
            consignee: "ACME",
            currency: "USD",
            route: "direct",
            routeLabel: "直接收汇",
            declarationCount: 1,
            declaredTotal: "100.00",
            receivedTotal: "103.00",
            outstanding: "-3.00",
            receivedFee: "0.00",
            receivedPercent: 100,
            receivedPercentText: "103%",
            oldestPendingText: "— · 全部已结汇",
            outstandingTone: "info",
          },
        ],
      }),
    ),
  );
  assert.match(customers, /103%/);
  assert.match(customers, /width:100%/);
  assert.match(customers, /view=declarations/);
  assert.match(customers, /全部已结汇/);
});
