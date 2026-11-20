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
  assert.match(registration, /待登记回款/);
  assert.match(registration, /已建批次/);
  assert.match(registration, /登记回款并建批次/);
  assert.match(registration, /name="targetAmount"/);
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
  assert.match(html, /href="\/settlement\/hk-transit\?batchNo=SB20261110-00012"[^>]*>去批次办资料/);
  assert.match(html, />去批次登记汇回</);
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

test("直接收汇保留客户总账，报关资料可通过 URL 定位同一复用资料组件", async () => {
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
  assert.match(docs, /报关资料清单/);
  assert.match(docs, /办理资料 · REAL872/);
  assert.match(docs, /当前客户范围：ACME/);
  assert.match(docs, /正在读取结汇资料/);
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
