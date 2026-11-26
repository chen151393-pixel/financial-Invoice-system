import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

let server, Jobs, Dialog;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  ({ CustomsImportJobs: Jobs } = await server.ssrLoadModule(
    "/src/modules/review/components/CustomsImportJobs.tsx",
  ));
  ({ CustomsImportDialog: Dialog } = await server.ssrLoadModule(
    "/src/modules/review/components/CustomsImportDialog.tsx",
  ));
});
after(() => server?.close());

const job = (status, extra = {}) => ({
  id: "1",
  fileName: "11月海关回执.xlsx",
  status,
  statusLabel: {
    pending: "等待后台处理",
    running: "正在解析与比对",
    completed: "导入成功",
    failed: "导入失败",
  }[status],
  error: "",
  result: null,
  ...extra,
});
const render = (value, error = "") => renderToStaticMarkup(createElement(Jobs, { jobs: [value], error }));

test("接收与处理中只显示等待后台完成，不冒充成功", () => {
  for (const status of ["pending", "running"]) {
    const html = render(job(status));
    assert.match(html, /尚未导入完成/);
    assert.match(html, /可关闭弹窗/);
    assert.doesNotMatch(html, /导入成功|已保存|data-tone="success"/);
  }
});

test("后台失败显式说明未导入、原有数据未替换并保留原因", () => {
  const html = render(job("failed", { error: "第3行成交数量不是有效数值" }));
  assert.match(html, /role="alert"/);
  assert.match(html, /第3行成交数量不是有效数值/);
  assert.match(html, /本文件未导入/);
  assert.match(html, /原有数据未被此文件替换/);
  assert.doesNotMatch(html, /导入成功|已保存/);
});

test("成功展示服务器返回的报关单数、明细数与逐张结果", () => {
  const html = render(
    job("completed", {
      result: {
        fileName: "11月海关回执.xlsx",
        rows: 24,
        created: 15,
        replaced: 0,
        unchanged: 0,
        columns: ["出口报关单号"],
        ignoredColumns: [],
        declarations: Array.from({ length: 15 }, (_, index) => ({
          declarationNo: `REAL${index}`,
          itemCount: index ? 1 : 10,
          resultLabel: "新增",
          status: "ns_missing",
          statusLabel: "未找到 NS 报关单",
          consignee: { state: "pending", label: "待关联" },
        })),
      },
    }),
  );
  assert.match(html, /导入成功/);
  assert.match(html, /已保存 15 张报关单、24 项明细/);
  assert.match(html, /REAL14/);
});

test("进度查询中断显示待核实，上传弹窗不再显示4MB或关闭并查看结果", () => {
  assert.match(render(job("pending"), "网络连接中断"), /暂时无法确认导入进度/);
  const html = renderToStaticMarkup(
    createElement(Dialog, {
      jobs: [],
      progressError: "",
      onClose() {},
      onQueued() {},
    }),
  );
  assert.match(html, /上传并后台导入/);
  assert.match(html, /24 列报关单明细/);
  assert.doesNotMatch(html, /4MB|关闭并查看结果|导入并匹配/);
});
