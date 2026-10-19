import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter as Router } from "react-router";
import { createServer } from "vite";

let server, Table, money;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  ({ TaskFollowupTable: Table } = await server.ssrLoadModule(
    "/src/modules/task/components/TaskFollowupTable.tsx",
  ));
  ({ money } = await server.ssrLoadModule("/src/shared/format/money.ts"));
});
after(async () => {
  await server?.close();
});

const task = {
  id: "1",
  supplier: "隔离测试供应商",
  company: "测试采购公司",
  currency: "CNY",
  recordNumber: "CD001",
  orderNumbers: ["SUB001"],
  status: "partially_received",
  statusLabel: "部分收票",
  reason: "等待其余发票",
  outstandingAmount: "104000.000001",
  receiptPercent: "42.2",
  receiptBarPercent: "42.2",
  followupEmployee: "张采购",
  lastContactAt: "2026-10-09T08:20:00Z",
  waitingLabel: "已等待 18 天",
};
function render(tasks) {
  return renderToStaticMarkup(
    createElement(
      Router,
      null,
      createElement(Table, {
        groups: tasks.map((item) => ({ id: item.id, tasks: [item] })),
      }),
    ),
  );
}

test("全部分组平铺在同一七列表格，保留每个任务的详情入口及后端精度", () => {
  const html = render([task, { ...task, id: "2", supplier: "另一供应商" }]);
  assert.equal((html.match(/<table/g) || []).length, 1);
  assert.equal((html.match(/scope="col"/g) || []).length, 7);
  assert.ok(!html.includes("<details"));
  for (const text of [
    "另一供应商",
    "104,000.000001",
    "42.2%",
    "10-09 16:20",
    "通知经办：张采购",
    "已等待 18 天",
    'href="/tasks/1"',
    'href="/tasks/2"',
  ]) {
    assert.ok(html.includes(text), text);
  }
});
test("缺失数据不伪装为零或联系成功，超收展示真实百分比与后端限定条宽", () => {
  const missing = render([
    {
      ...task,
      outstandingAmount: null,
      receiptPercent: null,
      receiptBarPercent: null,
      followupEmployee: "",
      lastContactAt: null,
      waitingLabel: "已完成",
    },
  ]);
  for (const text of ["金额待确认", "进度待确认", "经办人未提供", "暂无联系记录", "已完成"])
    assert.ok(missing.includes(text));
  assert.ok(!missing.includes("width:0%"));
  const over = render([{ ...task, receiptPercent: "120", receiptBarPercent: "100" }]);
  assert.ok(over.includes("120%") && over.includes("width:100%"));
});

test("旧接口缺少新增跟进字段时仍显示任务和详情，不崩溃或伪造进度", () => {
  const legacyTask = { ...task };
  for (const field of [
    "outstandingAmount",
    "receiptPercent",
    "receiptBarPercent",
    "followupEmployee",
    "lastContactAt",
    "waitingLabel",
  ]) {
    delete legacyTask[field];
  }
  const html = render([legacyTask]);
  for (const text of [
    "隔离测试供应商",
    "金额待确认",
    "进度待确认",
    "联系记录待获取",
    "等待情况待获取",
    'href="/tasks/1"',
  ]) {
    assert.ok(html.includes(text), text);
  }
  assert.ok(!html.includes("undefined"));
  assert.ok(!html.includes("task-followup__track"));
  assert.ok(!html.includes("暂无联系记录"));
});

test("金额格式化兼容缺失值，并保留零金额、零进度和高精度金额", () => {
  for (const value of [undefined, null, ""]) assert.equal(money(value), "—");
  assert.equal(money("0"), "0.00");
  assert.equal(money("999999999999999999.123456"), "999,999,999,999,999,999.123456");
  const html = render([{ ...task, outstandingAmount: "0", receiptPercent: "0", receiptBarPercent: "0" }]);
  assert.ok(html.includes("0.00") && html.includes("width:0%"));
  assert.ok(!html.includes("金额待确认") && !html.includes("进度待确认"));
});
