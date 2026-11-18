import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { createServer } from "vite";

let server, navigation, subViewPath, ConsigneeSummary, LedgerGroupTable, LedgerSummaryTable, ReceivableStats;
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
});
after(() => server?.close());

test("结汇对账子菜单顺序：银行收汇明细在香港中转批次之前，直接收汇明细取代直接收汇批次", () => {
  const settlement = navigation.flatMap((group) => group.items).find((item) => item.id === "settlement");
  assert.deepEqual(
    settlement.children.map((child) => child.label),
    ["报关应收汇", "银行收汇明细", "香港中转批次", "直接收汇明细", "合同抬头"],
  );
  assert.equal(subViewPath("settlement-bank"), "/settlement/bank-receipts");
  assert.equal(subViewPath("settlement-direct"), "/settlement/direct");
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
  assert.match(html, /香港中转应收汇（USD）[\s\S]*431,150\.00[\s\S]*6 票 · 登记回款建批次/);
  assert.match(html, /香港中转待登记回款（USD）[\s\S]*231,600\.00[\s\S]*3 票尚未建批次/);
  assert.match(html, /直接收汇待收金额（USD）[\s\S]*22,350\.00/);
  assert.equal(renderToStaticMarkup(createElement(ReceivableStats, { totals: [], unsettled: [] })), "");
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
  assert.match(html, /<th[^>]*>余额<\/th><\/tr><\/thead>/);
  assert.match(exportRow, /<strong>56,900\.00<\/strong><\/td>$/);
  assert.match(html, /<strong>-5,100\.00<\/strong><\/td><\/tr>/);
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
    createElement(LedgerSummaryTable, { groups: [group, { ...group, currency: "EUR" }] }),
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
