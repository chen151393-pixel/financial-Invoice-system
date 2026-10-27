import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { createServer } from "vite";

let server, Todos, Page, Metrics, Kpis, api, paths, Queue, Filters, Nodes, WbQueue, Suppliers;
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
  ({ QueueFilters: Filters } = await server.ssrLoadModule(
    "/src/modules/matching/components/QueueFilters.tsx",
  ));
});
after(async () => {
  await server?.close();
});
const counts = { all: 3, review: 1, matching: 1, task: 1, blocked: 0, reverify: 0, preparation: 1 };
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
  const allocation = {
    id: "9",
    tier: "high",
    confidence: "90",
    quantity: "10",
    amount: "100.5",
    noteReasons: ["发票不含税价格高于申报价"],
    confirm: { allowed: true, reason: "通过时需填写说明" },
    purchase: { orderNo: "SUB-200", item: "墨水" },
  };
  const row = {
    allocation,
    invoiceId: "1",
    invoiceNumber: "2600",
    seller: "测试",
    itemName: "墨水",
    anomalies: ["价格"],
  };
  const html = render(Queue, { rows: [row], selected: [], onToggle() {}, onToggleAll() {} });
  assert.match(html, /aria-label="异常：价格"/);
  assert.match(html, /需说明：发票不含税价格高于申报价/);
  assert.match(html, /<input type="checkbox" aria-label="选择建议 9" disabled=""/);
  const filters = render(Filters, {
    value: { anomaly: "abnormal", supplierId: "", invoiceFrom: "", invoiceTo: "" },
    suppliers: [],
    busy: false,
    onApply() {},
  });
  assert.match(filters, /<option value="abnormal" selected="">只看异常/);
  assert.match(filters, /只看正常/);
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
        hint: "本月生成 3 个开票任务",
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
