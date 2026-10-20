import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { createServer } from "vite";

let server, api, http, Table, Header, Records, Dialog, NotConnected;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  const load = (path) => server.ssrLoadModule(`/src/modules/writeback/${path}`);
  api = await load("api.ts");
  http = await server.ssrLoadModule("/src/shared/api/http.ts");
  ({ WritebackTable: Table } = await load("components/WritebackTable.tsx"));
  ({ RequestHeader: Header } = await load("components/RequestHeader.tsx"));
  ({ ResultRecords: Records } = await load("components/ResultRecords.tsx"));
  ({ ConfirmDialog: Dialog } = await load("components/ConfirmDialog.tsx"));
  ({ NotConnected } = await load("components/NotConnected.tsx"));
});
after(async () => {
  await server?.close();
});

const render = (component, props) =>
  renderToStaticMarkup(createElement(MemoryRouter, null, createElement(component, props)));
const allowed = { allowed: true, reason: "" };
const item = (changes) => ({
  invoiceId: "1",
  invoiceNo: "26332000000412805519",
  invoiceDate: "2026-10-12",
  vendorName: "测试供应商",
  amount: "20,800.00",
  currency: "CNY",
  purchaseOrders: "PO-1",
  allocation: "2 / 2 已确认",
  phase: "ready",
  label: "可回写",
  requestId: null,
  note: null,
  preview: allowed,
  ...changes,
});
const request = (changes) => ({
  requestId: "WB-1",
  invoiceId: "1",
  invoiceNo: "26332000000412805519",
  invoiceDate: "2026-10-12",
  vendorName: "测试供应商",
  vendorRef: "NS 供应商 #1",
  invoiceAmount: "20,800.00",
  totalAmount: "20,800.00",
  currency: "CNY",
  account: "测试账套",
  phase: "pending",
  label: "待确认",
  message: "预览已生成，等待确认",
  createdAt: "2026-10-19T06:20:00Z",
  createdBy: "管理员",
  expiresAt: "2026-10-19T06:35:00Z",
  readAt: "2026-10-19T06:20:08Z",
  checks: [],
  lines: [],
  totalLabel: "合计",
  operations: ["新建 1 条供应商发票主记录"],
  execute: allowed,
  refresh: allowed,
  verify: allowed,
  records: [],
  bills: [],
  poll: false,
  events: [],
  ...changes,
});

test("只有后端未登记接口才算未接入，业务上的记录不存在不算", () => {
  assert.equal(api.isNotConnected(new http.HttpError("接口不存在", 404)), true);
  assert.equal(api.isNotConnected(new http.HttpError("不支持的请求方式", 405)), true);
  assert.equal(api.isNotConnected(new http.HttpError("未找到回写记录", 404)), false);
  assert.equal(api.isNotConnected(new Error("网络中断")), false);
});

test("未接入页说明限制且不显示任何记录", () => {
  const html = render(NotConnected, { scope: "回写列表暂无可用数据。" });
  assert.match(html, /NS 回写尚未接入/);
  assert.match(html, /不显示示例数据/);
  assert.doesNotMatch(html, /<table/);
});

test("列表按后端 allowed 禁用生成预览并就近显示原因", () => {
  const html = render(Table, {
    items: [
      item({ invoiceId: "1", preview: { allowed: false, reason: "还有 1 条分配待复核" }, phase: "blocked" }),
      item({ invoiceId: "2", phase: "unknown", label: "结果待核实", requestId: "WB-9", note: "NS 响应超时" }),
    ],
    busyInvoice: "",
    error: null,
    onPreview: () => {},
  });
  assert.match(
    html,
    /disabled=""[^>]*aria-describedby="wb-reason-1"|aria-describedby="wb-reason-1"[^>]*disabled=""/,
  );
  assert.match(html, /还有 1 条分配待复核/);
  assert.match(html, /href="\/writeback\/WB-9"[^>]*>核实结果/);
  assert.equal((html.match(/生成预览/g) ?? []).length, 1);
});

test("待确认时执行按钮服从后端原因；待核实只提供核实，不提供重新提交", () => {
  const props = {
    action: "",
    creating: false,
    onConfirm() {},
    onVerify() {},
    onRefresh() {},
    onRepreview() {},
  };
  const pending = render(Header, {
    ...props,
    data: request({ execute: { allowed: false, reason: "NS 写入未启用，只能查看预览" } }),
  });
  assert.match(pending, /<button[^>]*disabled=""[^>]*>确认回写 NS/);
  assert.match(pending, /NS 写入未启用，只能查看预览/);
  const unknown = render(Header, {
    ...props,
    data: request({ phase: "unknown", label: "结果待核实", message: "NS 响应超时" }),
  });
  assert.match(unknown, /核实 NS 结果/);
  assert.doesNotMatch(unknown, /重新生成预览|确认回写 NS/);
});

test("未回读的写入后金额显示为未回读，不显示为 0", () => {
  const html = render(Records, {
    data: request({
      phase: "unknown",
      bills: [
        {
          billNo: "VB-1",
          subPoNo: "SUB-1",
          before: "0.00",
          amount: "4,200.00",
          after: null,
          status: "待核实",
          passed: false,
        },
      ],
    }),
  });
  assert.match(html, /未回读/);
  assert.doesNotMatch(html, />0<\/td>/);
});

test("确认弹窗在勾选核对前不能提交", () => {
  const html = render(Dialog, { data: request(), busy: false, onCancel() {}, onConfirm() {} });
  assert.match(html, /写入后不能在本系统撤销/);
  assert.match(html, /<button[^>]*disabled=""[^>]*>确认回写<\/button>/);
});
