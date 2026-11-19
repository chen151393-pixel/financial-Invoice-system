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
  BankReceiptStats;
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
});
after(() => server?.close());

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

const total = (overrides) => ({
  consignee: "ACME LTD",
  currency: "USD",
  route: "direct",
  routeLabel: "直接收汇",
  routeBasis: "境外收货人非集团香港公司",
  handling: "ledger",
  handlingLabel: "进直接收汇明细",
  exportCompanies: ["上海毅烁"],
  count: 2,
  firstExportDate: "2026-10-13",
  lastExportDate: "2026-11-06",
  amount: "99200.00",
  batchedCount: 0,
  pendingCount: 0,
  issueCount: 0,
  ...overrides,
});

test("按境外收货人汇总：香港中转指向批次并显示建批次进度，直接收汇指向直接收汇明细", () => {
  const html = renderToStaticMarkup(
    inRouter(
      createElement(ConsigneeSummary, {
        rows: [
          total({
            consignee: "HONGKONG VISION",
            route: "hk_transit",
            routeLabel: "香港中转",
            routeBasis: "境外收货人为集团香港公司",
            handling: "batch",
            count: 3,
            amount: "256850.00",
            batchedCount: 1,
            pendingCount: 2,
            issueCount: 1,
          }),
          total({}),
        ],
      }),
    ),
  );
  assert.match(html, /href="\/settlement\/hk-transit"[^>]*>香港中转批次/);
  assert.match(html, /1 票已建批次 · 2 票待登记回款/);
  assert.match(html, /1 张金额缺失未计入/);
  assert.match(html, /USD 256,850\.00/);
  assert.match(html, /href="\/settlement\/direct"[^>]*>直接收汇明细/);
  assert.match(html, /2026-10-13 至 2026-11-06/);
  assert.match(html, /境外收货人非集团香港公司/);
});

test("应收汇概况只展示后端汇总：按路径分卡，香港中转另列待登记回款", () => {
  const html = renderToStaticMarkup(
    createElement(ReceivableStats, {
      combinedTotals: [{ count: 14, currency: "USD", amount: "776450.00" }],
      totals: [
        { route: "direct", routeLabel: "直接收汇", count: 8, currency: "USD", amount: "345300.00" },
        { route: "hk_transit", routeLabel: "香港中转", count: 6, currency: "USD", amount: "431150.00" },
      ],
      unsettled: [
        { route: "direct", routeLabel: "直接收汇", count: 8, currency: "USD", amount: "345300.00" },
        { route: "hk_transit", routeLabel: "香港中转", count: 3, currency: "USD", amount: "231600.00" },
      ],
      directTotals: [{ currency: "USD", outstanding: "22350.00", balance: "-435725.67" }],
    }),
  );
  assert.match(html, /直接收汇应收汇（USD）[\s\S]*345,300\.00[\s\S]*8 票 · 进直接收汇明细/);
  assert.match(html, /报关应收汇（总）（USD）[\s\S]*776,450\.00[\s\S]*14 票 · 香港中转 \+ 直接收汇/);
  assert.match(html, /香港中转应收汇（USD）[\s\S]*431,150\.00[\s\S]*6 票 · 进香港中转批次登记/);
  assert.match(html, /香港中转待登记回款（USD）[\s\S]*231,600\.00[\s\S]*3 票尚未建批次/);
  assert.match(html, /直接收汇待收金额（USD）[\s\S]*22,350\.00/);
  assert.equal(
    renderToStaticMarkup(createElement(ReceivableStats, { totals: [], combinedTotals: [], unsettled: [] })),
    "",
  );
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

test("报关应收页不再登记回款；香港待登记页提供勾选与登记入口", async () => {
  const { CandidatePanel } = await server.ssrLoadModule(
    "/src/modules/settlement/components/CandidatePanel.tsx",
  );
  const { SettlementHkTransitPage } = await server.ssrLoadModule(
    "/src/modules/settlement/pages/SettlementHkTransitPage.tsx",
  );
  const browse = renderToStaticMarkup(inRouter(createElement(CandidatePanel, { mode: "receivables" })));
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
});

test("报关单明细只在登记区域允许勾选，并保留后端不可选原因", async () => {
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
  const browse = renderToStaticMarkup(inRouter(createElement(CandidateTable, { rows })));
  assert.doesNotMatch(browse, /type="checkbox"/);
  assert.match(browse, /tab=receipts/);
  assert.match(browse, /consignee=HK\+%26\+CO/);
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
