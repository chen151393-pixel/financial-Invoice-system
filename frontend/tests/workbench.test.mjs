import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { createServer } from "vite";

let server, Todos, Page, Metrics, Kpis, api, paths, Queue, Filters, Nodes, WbQueue, Suppliers, Unbound;
let Checks, Candidates, LineNav, matchingApi;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  ({ WorkbenchTodos: Todos } = await server.ssrLoadModule(
    "/src/modules/matching/components/WorkbenchTodos.tsx",
  ));
  ({ WorkbenchNodes: Nodes } = await server.ssrLoadModule(
    "/src/modules/matching/components/WorkbenchNodes.tsx",
  ));
  ({ WorkbenchQueue: WbQueue } = await server.ssrLoadModule(
    "/src/modules/matching/components/WorkbenchQueue.tsx",
  ));
  ({ WorkbenchSuppliers: Suppliers } = await server.ssrLoadModule(
    "/src/modules/matching/components/WorkbenchSuppliers.tsx",
  ));
  ({ WorkbenchUnboundNotify: Unbound } = await server.ssrLoadModule(
    "/src/modules/matching/components/WorkbenchUnboundNotify.tsx",
  ));
  ({ WorkbenchPage: Page } = await server.ssrLoadModule("/src/modules/matching/pages/WorkbenchPage.tsx"));
  api = await server.ssrLoadModule("/src/modules/matching/api/workbench-api.ts");
  ({ WorkbenchKpis: Kpis } = await server.ssrLoadModule(
    "/src/modules/matching/components/WorkbenchKpis.tsx",
  ));
  ({ WorkbenchMetrics: Metrics } = await server.ssrLoadModule(
    "/src/modules/matching/components/WorkbenchMetrics.tsx",
  ));
  paths = await server.ssrLoadModule("/src/app/paths.ts");
  ({ QueueTable: Queue } = await server.ssrLoadModule("/src/modules/matching/components/QueueTable.tsx"));
  ({ ChecksTable: Checks } = await server.ssrLoadModule("/src/modules/matching/components/ChecksTable.tsx"));
  ({ CandidateTable: Candidates } = await server.ssrLoadModule(
    "/src/modules/matching/components/CandidateTable.tsx",
  ));
  ({ InvoiceLineNav: LineNav } = await server.ssrLoadModule(
    "/src/modules/matching/components/InvoiceLineNav.tsx",
  ));
  matchingApi = await server.ssrLoadModule("/src/modules/matching/api/index.ts");
  ({ QueueFilters: Filters } = await server.ssrLoadModule(
    "/src/modules/matching/components/QueueFilters.tsx",
  ));
});
after(async () => {
  await server?.close();
});
const counts = { all: 3, review: 1, matching: 1, task: 1, blocked: 0, reverify: 0, preparation: 1 };

test("月度收票趋势区分无应开和真实零收票，直接显示精确金额与低收票率", async () => {
  const { WorkbenchReceipts } = await server.ssrLoadModule(
    "/src/modules/matching/components/WorkbenchReceipts.tsx",
  );
  const monthly = [
    { month: "2026-08", expected: "0", received: "0", percent: null, unknownTasks: 2 },
    { month: "2026-09", expected: "100.00", received: "0", percent: "0.0", unknownTasks: 0 },
    { month: "2026-10", expected: "920000.00", received: "11040.00", percent: "1.2", unknownTasks: 0 },
  ];
  const html = renderToStaticMarkup(createElement(WorkbenchReceipts, { monthly, unknownExpectedDates: 3 }));
  assert.match(html, /920,000.00/);
  assert.match(html, /11,040.00/);
  assert.match(html, /1.2%/);
  assert.match(html, /应开按报关单创建月/);
  assert.match(html, /3 个人民币任务未取得关联报关单的创建日期/);
  assert.match(html, /value="2026-10" selected=""/);
  assert.equal((html.match(/class="ui-chart__point"/g) ?? []).length, 2);
  assert.match(html, /收票／应开比 暂无应开/);
  assert.match(html, /0.0%/);
  assert.match(html, /另有 2 个任务应开金额缺失/);
  const empty = renderToStaticMarkup(createElement(WorkbenchReceipts, { monthly: [monthly[0]] }));
  assert.match(empty, /暂无可统计的应开或收票金额/);
  assert.doesNotMatch(empty, /class="ui-chart"/);
  const noMonths = renderToStaticMarkup(createElement(WorkbenchReceipts, { monthly: [] }));
  assert.match(noMonths, /暂无可统计的应开或收票金额/);
  const onlyInvoices = renderToStaticMarkup(
    createElement(WorkbenchReceipts, {
      monthly: [{ ...monthly[0], received: "123.45" }],
    }),
  );
  assert.match(onlyInvoices, /123.45/);
  assert.match(onlyInvoices, /class="ui-chart"/);
  assert.doesNotMatch(onlyInvoices, /class="ui-chart__point"/);
});

test("折线空值形成断点，孤立有效点与真实零值仍保留", async () => {
  const { TrendChart } = await server.ssrLoadModule("/src/shared/components/ui/charts/TrendChart.tsx");
  const html = renderToStaticMarkup(
    createElement(TrendChart, {
      label: "断点验证",
      categories: ["5月", "6月", "7月", "8月", "9月", "10月"],
      lineAxis: "percent",
      line: { key: "rate", label: "收票率", values: [0, 10, null, 30, null, 1.2] },
    }),
  );
  assert.equal((html.match(/<polyline/g) ?? []).length, 1);
  assert.equal((html.match(/class="ui-chart__point"/g) ?? []).length, 4);
  assert.equal((html.match(/tabindex="0"/g) ?? []).length, 6);
  assert.doesNotMatch(html, /NaN|undefined/);
  const over = renderToStaticMarkup(
    createElement(TrendChart, {
      label: "超过百分百",
      categories: ["10月"],
      lineAxis: "percent",
      line: { key: "ratio", label: "收票／应开比", values: [140] },
    }),
  );
  assert.match(over, /150%/);
});

test("审核队列请求整票接口并保留后端分页与日期条件", async (t) => {
  let seen;
  t.mock.method(globalThis, "fetch", async (url, options) => {
    seen = { url, body: JSON.parse(options.body) };
    return Response.json({ rows: [], total: 0 });
  });
  await matchingApi.getMatchingQueue({
    invoiceNo: "001,002",
    supplierName: "上海;杭州",
    tier: "low",
    anomaly: "abnormal",
    supplierId: "7",
    invoiceFrom: "",
    invoiceTo: "",
    page: 3,
    pageSize: 10,
  });
  assert.equal(seen.url, "/api/matching/invoice-queue/query");
  assert.deepEqual(seen.body, {
    invoiceNo: "001,002",
    supplierName: "上海;杭州",
    tier: "low",
    anomaly: "abnormal",
    supplierId: "7",
    invoiceFrom: null,
    invoiceTo: null,
    page: 3,
    pageSize: 10,
  });
});

test("逐项比对默认展示原始金额和差异，异常说明可见", () => {
  const html = render(Checks, {
    caption: "逐项比对",
    checks: [
      {
        key: "amount",
        label: "含税金额",
        invoiceValue: "1234567890.12",
        purchaseValue: "1234567890.10",
        result: "mismatch",
        difference: "0.02",
        note: "金额需核实",
        resultLabel: "不一致",
        differenceLabel: "发票多 0.02",
      },
    ],
  });
  assert.match(html, /1234567890.12/);
  assert.match(html, /发票多 0.02/);
  assert.match(html, /金额需核实/);
  assert.doesNotMatch(html, /<details/);
});

test("分次收票显示后端结果文字和剩余说明，不显示负数差额", () => {
  const html = render(Checks, {
    caption: "逐项比对",
    checks: [
      {
        key: "quantity",
        label: "数量",
        invoiceValue: "72",
        purchaseValue: "192",
        result: "match",
        difference: "-120",
        note: "本次数量在剩余应开范围内可分次收票",
        resultLabel: "分次收票",
        differenceLabel: "收票后剩余应开 120",
      },
    ],
  });
  assert.match(html, /分次收票/);
  assert.match(html, /收票后剩余应开 120/);
  assert.doesNotMatch(html, /-120/);
  assert.doesNotMatch(html, />一致</);
});

test("明细导航保持选中行；提交期间禁止切换，候选限制取后端", () => {
  const html = render(LineNav, {
    items: [
      {
        id: "1",
        lineNo: "1",
        item: "墨水",
        active: true,
        amount: "100.50",
        quantity: "10",
        unit: "个",
        allocations: [],
      },
    ],
    groups: [],
    selectedId: "1",
    busy: true,
    onSelect() {},
  });
  assert.match(html, /aria-current="true"/);
  assert.match(html, /disabled=""/);
  const candidates = render(Candidates, {
    rows: [
      {
        purchaseOrderId: "3",
        orderNo: "SUB-3",
        parentOrderNo: "PO-3",
        supplier: "测试供应商",
        recordNumbers: ["CD3"],
        currency: "CNY",
        unit: "个",
        remainingQuantity: "30",
        remainingAmount: "301.50",
        orderMatched: true,
        confidence: "60",
        checks: [],
        block: "币种待核实",
        lines: [{ purchaseLineId: "31" }, { purchaseLineId: "32" }],
      },
    ],
    chosenId: null,
    onChoose() {},
  });
  // 候选以整张子采购单为一行：显示母单、明细行数与整单剩余应开，限制取后端
  assert.match(candidates, /SUB-3/);
  assert.match(candidates, /母采购单 PO-3/);
  assert.match(candidates, /2 行/);
  assert.match(candidates, /301.50 CNY/);
  assert.match(candidates, /备注命中/);
  assert.match(candidates, /币种待核实/);
  assert.match(candidates, /disabled=""[^>]*>选择此单/);
});
const row = {
  key: "review:1",
  kind: "review",
  targetId: "1",
  title: "CD A&1",
  subtitle: "PL-1",
  party: "测试供应商",
  account: "A",
  amount: null,
  currency: "",
  amountLabel: "按子采购行核对",
  statusLabel: "待财务核对",
  reason: "核实依据",
  attention: false,
  role: "finance",
  waitingDays: 4,
};
const data = {
  counts,
  filteredCounts: counts,
  items: [
    row,
    { ...row, key: "matching:2", kind: "matching", targetId: "2" },
    {
      ...row,
      key: "task:3",
      kind: "task",
      targetId: "3",
      amount: "9007199254740993.123456",
      currency: "CNY",
      role: "purchase",
      waitingDays: null,
    },
  ],
  total: 3,
  page: 1,
  pages: 1,
  pageSize: 5,
  suppliers: [],
  unknownSupplierAmounts: 0,
};
const query = {
  account: "",
  supplierId: "",
  createdFrom: "",
  createdTo: "",
  keyword: "",
  kind: "all",
  sort: "priority",
  page: 1,
  pageSize: 5,
};
// 后端按报关单位置累加得出的六步漏斗
const funnel = {
  completionRate: "40.0",
  steps: [
    { key: "synced", label: "已入库待开票报关单", count: 10, rate: null, stuck: [] },
    {
      key: "approved",
      label: "财务审核通过",
      count: 8,
      rate: "80.0",
      stuck: [{ key: "pending_review", label: "待财务审核", count: 2 }],
    },
    { key: "archived", label: "子采购合同归档", count: 8, rate: "100.0", stuck: [] },
    {
      key: "notified",
      label: "已通知供应商",
      count: 7,
      rate: "87.5",
      stuck: [{ key: "notification", label: "待通知供应商", count: 1 }],
    },
    {
      key: "invoiced",
      label: "已收到发票",
      count: 4,
      rate: "57.1",
      stuck: [{ key: "invoices", label: "待供应商开票", count: 3 }],
    },
    { key: "completed", label: "资料齐全完结", count: 4, rate: "100.0", stuck: [] },
  ],
};
const render = (component, props) =>
  renderToStaticMarkup(createElement(MemoryRouter, null, createElement(component, props)));

test("待办真实下钻到核对、发票比对和任务详情，金额保留精度", () => {
  const html = render(Todos, { data, query, change() {}, onExport() {}, exporting: false });
  assert.match(html, /href="\/review\?keyword=CD\+A%261"/);
  assert.match(html, /href="\/matching\/2"/);
  assert.match(html, /href="\/tasks\/3"/);
  assert.match(html, /9,007,199,254,740,993.123456/);
  assert.match(html, /按子采购行核对/);
  // 处理方标签与等待天数来自后端；已完成等没有天数的显示“—”
  assert.match(html, /财务<\/span>待核对/);
  assert.match(html, /采购<\/span>待开票/);
  assert.match(html, />4 天</);
  assert.doesNotMatch(html, /模拟审核|超期/);
});

test("待办空结果明确显示，导出禁用", () => {
  const html = render(Todos, {
    data: { ...data, items: [], total: 0 },
    query,
    change() {},
    onExport() {},
    exporting: false,
  });
  assert.match(html, /当前条件下没有待办/);
  assert.match(html, /disabled=""[^>]*>↓ 导出全部结果/);
});

test("初始加载不显示伪造零指标或空结果", () => {
  const html = render(Page, {
    state: { query, loading: true, data: null, error: "", change() {}, refresh() {} },
  });
  assert.match(html, /正在读取工作台数据/);
  assert.doesNotMatch(html, /共 0 项|当前条件下没有待办/);
});

test("查询与导出携带相同筛选，导出结果完全取自后端", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return Response.json(
      url.endsWith("export") ? { filename: "result.csv", content: "真实导出", count: 52 } : data,
    );
  });
  const selected = { ...query, account: "A", keyword: "供应商", page: 2, supplierId: "7" };
  await api.queryWorkbench(selected);
  assert.equal((await api.exportWorkbench(selected)).count, 52);
  // 未填写的日期提交 null，由后端按"不限"处理
  const sent = { ...selected, createdFrom: null, createdTo: null };
  assert.deepEqual(
    calls.map((call) => call.body),
    [sent, sent],
  );
  assert.deepEqual(
    calls.map((call) => call.url),
    ["/api/matching/workbench/query", "/api/matching/workbench/export"],
  );
});

test("业务流程漏斗展示六步计数、通过率与完结率，卡点链接到核对或开票跟进节点", () => {
  const html = render(Metrics, { funnel, noTaskCount: 2 });
  for (const label of ["已入库待开票报关单", "子采购合同归档", "资料齐全完结", "上一环节通过 87.5%"])
    assert.ok(html.includes(label), label);
  assert.match(html, /整体完结率 <strong>40.0%<\/strong>/);
  assert.match(html, /href="\/review\?status=pending"[^>]*>2 张待财务审核 →/);
  assert.match(html, /href="\/tasks\?node=invoices"[^>]*>3 张待供应商开票 →/);
  assert.match(html, /另有 2 张无需开票/);
  assert.equal((html.match(/起点/g) || []).length, 1);
});

test("列表地址只写入已填写的筛选条件", () => {
  assert.equal(paths.taskListPath({ stage: "notify", supplierId: "" }), "/tasks?stage=notify");
  assert.equal(paths.reviewListPath({}), "/review");
  assert.equal(paths.taskListPath({ node: "documents" }), "/tasks?node=documents");
  assert.equal(paths.matchingQueuePath({ tier: "high" }), "/matching?tier=high");
  assert.equal(paths.matchingQueuePath({}), "/matching");
});

test("比对队列显示异常分类，异常建议不能勾选批量通过；筛选含只看异常", () => {
  const row = {
    invoice: { id: "1", number: "2600", seller: "测试", date: "2026-10-28", gross: "100.5", currency: "CNY" },
    proposalCount: 8,
    purchaseOrders: ["SUB-200", "SUB-201"],
    tier: "high",
    confidence: "90",
    batch: { allowed: false, reason: "请进入详情逐行核对" },
    batchIds: [],
    anomalies: ["价格"],
  };
  const html = render(Queue, { rows: [row], selected: [], onToggle() {}, onToggleAll() {} });
  assert.match(html, /aria-label="异常：价格"/);
  assert.match(html, /请进入详情逐行核对/);
  assert.match(html, /<input type="checkbox" aria-label="选择发票 2600" disabled=""/);
  assert.equal((html.match(/>2600<\/strong>/g) || []).length, 1);
  assert.match(html, /8 条/);
  assert.match(html, /href="\/matching\/1"/);
  const filters = render(Filters, {
    value: {
      anomaly: "abnormal",
      invoiceNo: "001,002",
      supplierName: "甲;乙",
      invoiceFrom: "",
      invoiceTo: "",
    },
    busy: false,
    onApply() {},
  });
  assert.match(filters, /<option value="abnormal" selected="">只看异常/);
  assert.match(filters, /只看正常/);
  assert.equal((filters.match(/type="search"/g) || []).length, 2);
  assert.match(filters, /value="001,002"/);
  assert.match(filters, /value="甲;乙"/);
  assert.match(filters, /<span class="ui-sr-only">发票号码<\/span>/);
  assert.match(filters, /<span class="ui-sr-only">供应商<\/span>/);
  assert.doesNotMatch(filters, /全部供应商/);
});

test("漏斗上一环节为 0 时说明暂无通过率，只有第一步标为起点", () => {
  const html = render(Metrics, {
    funnel: {
      completionRate: "0.0",
      steps: [
        { key: "synced", label: "已入库待开票报关单", count: 158, rate: null, stuck: [] },
        { key: "approved", label: "财务审核通过", count: 3, rate: "1.9", stuck: [] },
        { key: "archived", label: "子采购合同归档", count: 0, rate: "0.0", stuck: [] },
        { key: "notified", label: "已通知供应商", count: 0, rate: null, stuck: [] },
      ],
    },
    noTaskCount: 0,
  });
  assert.equal((html.match(/起点/g) || []).length, 1);
  assert.match(html, /上一环节为 0，暂无通过率/);
  assert.match(html, /aria-label="业务流程横向条形图"/);
  assert.equal((html.match(/class="ui-hbar__bar" style="width:0%/g) || []).length, 2);
  assert.match(html, /class="ui-hbar__bar" style="width:1.5%/);
  assert.match(html, /class="ui-hbar__value">3<\/span>/);
});

test("关键指标：首张实底主指标，金额格式化后端值，标签区分财务与采购", () => {
  const kpi = {
    role: "finance",
    unit: "",
    currency: "CNY",
    direction: "up",
    tone: "neutral",
    series: ["0", "1", "2"],
  };
  const html = render(Kpis, {
    kpis: [
      {
        ...kpi,
        key: "expected",
        label: "本月应开金额",
        value: "3286400.5",
        delta: "较上月 +12.4%",
        hint: "本月创建报关单关联 3 个开票任务",
      },
      {
        ...kpi,
        key: "notify",
        label: "待通知供应商",
        role: "purchase",
        value: "11",
        unit: "个",
        currency: "",
        direction: "flat",
        tone: "warning",
        delta: "另有 1 个待存合同",
        hint: "合同已归档，可通知供应商开票",
      },
    ],
  });
  assert.equal((html.match(/ui-metric--solid/g) || []).length, 1);
  assert.match(html, /¥ 3,286,400.50/);
  assert.match(html, /较上月 \+12.4%/);
  assert.match(html, />财务</);
  assert.match(html, />采购</);
  assert.match(html, /data-tone="warning"[^>]*>.*另有 1 个待存合同/);
});

test("节点分布、比对队列与供应商排行只展示后端计数和比例", () => {
  const nodes = render(Nodes, {
    nodes: {
      total: 4,
      nodes: [
        { key: "documents", label: "待存合同", count: 1, percent: "25.0" },
        { key: "invoices", label: "待供应商开票", count: 3, percent: "75.0" },
      ],
    },
  });
  assert.match(nodes, /待供应商开票/);
  assert.match(nodes, /3 · 75.0%/);
  const queue = render(WbQueue, {
    queue: { all: 5, high: 3, medium: 1, low: 1, anomalies: [{ label: "单位", count: 2, percent: "100.0" }] },
  });
  assert.match(queue, /高置信度 3 条，去队列批量通过 →/);
  assert.match(queue, /href="\/matching\?tier=high"/);
  assert.match(queue, /单位不一致/);
  const empty = render(WbQueue, { queue: { all: 0, high: 0, medium: 0, low: 0, anomalies: [] } });
  assert.match(empty, /比对项全部一致/);
  assert.match(empty, /去比对审核队列 →/);
  const suppliers = render(Suppliers, {
    data: {
      ...data,
      suppliers: [
        {
          key: "A:1:CNY",
          supplier: "供应商甲",
          account: "A",
          currency: "CNY",
          amount: "286400",
          percent: "100.0",
          longestDays: 21,
          overdue: true,
        },
      ],
    },
  });
  assert.match(suppliers, /¥ 286,400.00/);
  assert.match(suppliers, /is-overdue">最长 21 天/);
  assert.match(suppliers, /data-tone="warning"/);
});

test("未绑群提醒显示后端计数与名单，链接到供应商档案未绑定筛选；为 0 时不显示", () => {
  const html = render(Unbound, {
    data: { suppliers: 7, tasks: 12, names: ["甲公司", "乙公司", "丙公司", "丁公司", "戊公司"] },
  });
  assert.match(html, /7 家供应商未绑定企微开票群，12 个待通知任务无法发出/);
  assert.match(html, /甲公司、乙公司、丙公司、丁公司、戊公司 等 7 家/);
  assert.ok(html.includes(`href="${paths.paths.supplierGroups}?status=unbound"`));
  assert.match(html, /data-tone="warning"/);
  const exact = render(Unbound, { data: { suppliers: 1, tasks: 1, names: ["甲公司"] } });
  assert.doesNotMatch(exact, /等 1 家/);
  assert.equal(render(Unbound, { data: { suppliers: 0, tasks: 0, names: [] } }), "");
});
