import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter as Router } from "react-router";
import { createServer } from "vite";

let server, api, queryState, RecoveryStats, RecoveryCharts, RecoveryTable, RecoverySearch, paths;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  api = await server.ssrLoadModule("/src/modules/task/api/recovery.ts");
  queryState = await server.ssrLoadModule("/src/modules/task/hooks/recovery-query.ts");
  ({ RecoveryStats } = await server.ssrLoadModule("/src/modules/task/components/RecoveryStats.tsx"));
  ({ RecoveryCharts } = await server.ssrLoadModule("/src/modules/task/components/RecoveryCharts.tsx"));
  ({ RecoveryTable } = await server.ssrLoadModule("/src/modules/task/components/RecoveryTable.tsx"));
  ({ RecoverySearch } = await server.ssrLoadModule("/src/modules/task/components/RecoverySearch.tsx"));
  paths = await server.ssrLoadModule("/src/app/paths.ts");
});
after(async () => {
  await server?.close();
});

const summary = (tasks, amount, suppliers = 1, unknown = 0) => ({ tasks, suppliers, amount, unknown });
const task = (id, values = {}) => ({
  taskId: id,
  recordNo: `CD${id}`,
  orders: [`POE${id}`],
  expected: "100.00",
  received: "0.00",
  outstanding: "100.00",
  approvedOn: "2026-10-19",
  dueDate: "2026-11-30",
  collected: false,
  node: "invoices",
  nodeLabel: "待供应商开票",
  ...values,
});
const board = {
  today: "2026-11-09",
  month: "2026-10",
  monthLabel: "10月开票",
  dueDate: "2026-11-30",
  defaultMonth: "2026-10",
  cards: {
    due: summary(333, "20834128.46", 168),
    collected: { ...summary(278, "18299491.76", 150), rate: 83.5 },
    outstanding: { ...summary(55, "2534636.70", 24, 2), daysLeft: 21 },
    overdue: { ...summary(10, "388626.70", 3), longOverdue: 1, months: ["8月", "9月"] },
  },
  months: [
    {
      month: "2026-08",
      label: "8月",
      dueDate: "2026-09-30",
      state: "closed",
      tasks: 321,
      collected: 300,
      rate: 93.5,
      expected: "100",
      collectedAmount: "90",
      outstandingAmount: "10",
      unknown: 0,
    },
    {
      month: "2026-11",
      label: "11月",
      dueDate: "2026-12-31",
      state: "open",
      tasks: 0,
      collected: 0,
      rate: null,
      expected: "0.00",
      collectedAmount: "0.00",
      outstandingAmount: "0.00",
      unknown: 0,
    },
  ],
  recentRate: 87.2,
  buyers: [
    { memberId: "5", name: "朱新卫", tasks: 75, outstanding: 1, rate: 98.7 },
    { memberId: "6", name: "纪琴", tasks: 160, outstanding: 49, rate: 69.4 },
    { memberId: "none", name: "未指定", tasks: 0, outstanding: 0, rate: null },
  ],
  concentration: {
    amount: "2534636.70",
    suppliers: 24,
    top: [{ supplierId: 1, name: "任丘市科迈五金制品厂", amount: "388691.60", share: 15.3 }],
    topAmount: "388691.60",
    topShare: 15.3,
    restSuppliers: 23,
    restAmount: "2145945.10",
    restShare: 84.7,
  },
  list: {
    view: "outstanding",
    summary: summary(55, "2534636.70", 24),
    items: [],
    total: 0,
    page: 1,
    pageSize: 10,
    pages: 1,
  },
  options: {
    buyers: [
      { id: "5", name: "朱新卫" },
      { id: "none", name: "未指定采购员" },
    ],
    companies: [{ id: "3", name: "绎视" }],
    months: [{ id: "2026-11", name: "11月" }],
  },
};
const render = (element) => renderToStaticMarkup(createElement(Router, null, element));

test("看板接口路径与地址条件往返", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return Response.json({ error: "测试错误" }, { status: 503 });
  });
  const query = { ...queryState.initialRecoveryQuery, month: "all", memberId: "none", orderNo: "POE1" };
  await assert.rejects(api.queryRecovery(query), /测试错误/);
  await assert.rejects(api.exportRecovery(query), /测试错误/);
  assert.deepEqual(
    calls.map((call) => call.url),
    ["/api/task/recovery/query", "/api/task/recovery/export"],
  );
  assert.equal(calls[0].body.memberId, "none");
  const params = queryState.writeRecoveryQuery({ ...query, view: "overdue", page: 2 });
  assert.equal(params.toString(), "month=all&memberId=none&orderNo=POE1&view=overdue&page=2");
  assert.deepEqual(queryState.readRecoveryQuery(params), { ...query, view: "overdue", page: 2 });
  assert.equal(queryState.readRecoveryQuery(new URLSearchParams("view=fake&page=0")).view, "outstanding");
  assert.equal(paths.viewPath("invoice-recovery"), "/invoice-recovery");
});

test("概况卡展示后端数字并以选中状态表示当前清单", () => {
  const markup = render(
    createElement(RecoveryStats, { board, view: "outstanding", disabled: false, onSelect() {} }),
  );
  assert.match(markup, /10月开票应收回/);
  assert.match(markup, /333 个/);
  assert.match(markup, /¥2,534,636.70 · 24 家 · 剩 21 天 · 2 个金额待确认/);
  assert.match(markup, /逾期未收回 · 8月、9月开票/);
  assert.match(markup, /超 30 天 1 个/);
  assert.equal(markup.match(/aria-pressed="true"/g).length, 1);
});

test("三张图卡：月份未到期标注、低回收率警示、集中度图例", () => {
  const markup = render(createElement(RecoveryCharts, { board, activeMember: "6", onBuyer() {} }));
  assert.match(markup, /按开票月份回收/);
  assert.doesNotMatch(markup, /通知月份|8月通知/);
  assert.match(markup, /93.5%/);
  assert.match(markup, /回收中/);
  assert.match(markup, /已到期月份平均 87.2%/);
  assert.match(markup, /data-low="">69.4%/);
  assert.match(markup, /aria-pressed="true">纪琴/);
  assert.match(markup, /任丘市科迈五金制品厂/);
  assert.match(markup, /其余 23 家/);
  assert.match(markup, /¥253.5万/);
});

test("清单按组展开，任务链接回开票跟进，超出部分折叠", () => {
  const group = {
    key: "1-3",
    supplierId: 1,
    supplierName: "任丘市科迈五金制品厂",
    companyId: 3,
    companyName: "绎视",
    memberId: "none",
    memberName: "未指定",
    tasks: 5,
    amount: "500.00",
    unknown: 0,
    approvedOn: "2026-10-19",
    dueDate: "2026-11-30",
    daysLeft: -3,
    items: ["1", "2", "3", "4", "5"].map((id) => task(id)),
  };
  const closed = render(
    createElement(RecoveryTable, {
      groups: [group],
      view: "outstanding",
      expanded: new Set(),
      onToggle() {},
    }),
  );
  assert.doesNotMatch(closed, /在开票跟进中查看/);
  assert.match(closed, /已逾期 3 天/);
  assert.match(closed, /未收回金额/);
  const open = render(
    createElement(RecoveryTable, { groups: [group], view: "due", expanded: new Set(["1-3"]), onToggle() {} }),
  );
  assert.match(open, /应开金额/);
  assert.match(open, /财务审核通过日期/);
  assert.match(open, /2026-10-19/);
  assert.doesNotMatch(open, /通知日期/);
  assert.equal(open.match(/在开票跟进中查看/g).length, 4);
  assert.match(open, /href="\/tasks\/1"/);
  assert.match(open, /显示其余 1 个任务/);
});

test("查询栏一行：月份分段含全部，采购员含未指定", () => {
  const markup = render(
    createElement(RecoverySearch, {
      board,
      query: { ...queryState.initialRecoveryQuery },
      busy: false,
      onSearch() {},
      onRefresh() {},
    }),
  );
  assert.match(markup, />全部</);
  assert.match(markup, /开票月份/);
  assert.doesNotMatch(markup, /通知月份/);
  const selectedMonths = [...markup.matchAll(/<button\b[^>]*aria-pressed="true"[^>]*>(.*?)<\/button>/g)];
  assert.deepEqual(
    selectedMonths.map((match) => match[1]),
    ["2026-10"],
  );
  assert.match(markup, /未指定采购员/);
  assert.match(markup, /CD 号 \/ 子采购单号/);
});
