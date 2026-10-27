import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

// 合成样本只用于组件验证，不连接真实 NS、共享盘或业务数据库。
let server, api, uploadApi, Declarations, Signed, Upload;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  api = await server.ssrLoadModule("/src/modules/task/api/task.ts");
  ({ DeclarationDocuments: Declarations } = await server.ssrLoadModule(
    "/src/modules/task/components/DeclarationDocuments.tsx",
  ));
  ({ SignedContracts: Signed } = await server.ssrLoadModule(
    "/src/modules/task/components/SignedContracts.tsx",
  ));
  uploadApi = await server.ssrLoadModule("/src/modules/task/api/signed-upload.ts");
  ({ SignedContractUpload: Upload } = await server.ssrLoadModule(
    "/src/modules/task/components/SignedContractUpload.tsx",
  ));
});
after(async () => {
  await server?.close();
});

const allowed = { allowed: true, reason: "从 NS 下载并保存到共享盘" };
const documents = [
  {
    type: "customs_declaration",
    label: "报关单",
    status: "archived",
    statusLabel: "已保存到共享盘",
    files: [{ filename: "报关单_CD870.pdf", path: "\\\\share\\2026年09月\\CD870_REAL870\\报关单_CD870.pdf" }],
    error: "",
    attempts: 1,
    archivedAt: "2026-10-23T01:00:00Z",
    retry: { allowed: true, reason: "重新从 NS 下载；内容不同时不覆盖已归档文件" },
  },
  {
    type: "sales_contract",
    label: "销售合同",
    status: "failed",
    statusLabel: "下载失败",
    files: [],
    error: "NS 中暂无该报关单的销售合同文件，请在 NS 补齐后重试",
    attempts: 2,
    archivedAt: null,
    retry: allowed,
  },
  {
    type: "invoice",
    label: "发票",
    status: "pending",
    statusLabel: "待下载",
    files: [],
    error: "",
    attempts: 0,
    archivedAt: null,
    retry: { allowed: false, reason: "报关资料下载接口尚未配置" },
  },
];

test("报关资料逐项显示状态、失败原因与路径，每项可单独重试或重新下载", () => {
  const html = renderToStaticMarkup(createElement(Declarations, { documents, busy: null, onRetry() {} }));
  assert.match(html, /CD870_REAL870/);
  assert.match(html, /失败原因：NS 中暂无该报关单的销售合同文件/);
  assert.match(html, /已尝试 2 次/);
  assert.match(html, /aria-label="重新下载报关单"/);
  assert.match(html, /aria-label="下载销售合同"[^>]*>重试下载/);
  // 接口未配置：按钮禁用并写明原因，不冒充可下载
  assert.match(html, /<button[^>]*disabled=""[^>]*aria-label="下载发票"/);
  assert.match(html, /报关资料下载接口尚未配置/);
  assert.match(html, /下载失败不影响通知供应商/);
});

test("回签合同按子采购单显示是否已上传，并提供上传入口", () => {
  const contracts = [
    {
      orderId: "1",
      orderNumber: "SUB-200",
      uploaded: true,
      filename: "回签合同_SUB-200.pdf",
      archivePath: "\\\\share\\CD870_REAL870\\回签合同_SUB-200.pdf",
      uploadedAt: "2026-10-23T02:00:00Z",
      uploadedBy: "user:admin",
    },
    {
      orderId: "2",
      orderNumber: "SUB-201",
      uploaded: false,
      filename: "",
      archivePath: null,
      uploadedAt: null,
      uploadedBy: "",
    },
  ];
  const html = renderToStaticMarkup(createElement(Signed, { contracts, disabled: false, onUpload() {} }));
  assert.match(html, /SUB-200[\s\S]*已上传 · user:admin/);
  assert.match(html, /SUB-201[\s\S]*尚未上传/);
  assert.match(html, /上传回签合同/);
});

test("上传窗口说明格式、大小与不覆盖规则，未选择文件时不能提交", () => {
  const html = renderToStaticMarkup(createElement(Upload, { onClose() {} }));
  assert.match(html, /批量上传回签合同/);
  assert.match(html, /PDF、JPG、PNG/);
  assert.match(html, /不会覆盖/);
  assert.match(html, /100 MB/);
  assert.match(html, /后台队列/);
  assert.match(html, /<input type="file" multiple=""/);
  assert.match(html, /<button[^>]*disabled=""[^>]*>上传 0 个文件/);
});

test("报关资料重试与回签上传只提交必要字段，失败时返回后端原因", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return Response.json({ error: "报关资料下载接口尚未配置" }, { status: 503 });
  });
  await assert.rejects(api.prepareDeclarationDocument("12", "invoice"), /尚未配置/);
  await assert.rejects(
    uploadApi.createSignedUpload("test-request", [{ filename: "SUB-200.pdf", size: 200000 }]),
    /尚未配置/,
  );
  assert.deepEqual(calls, [
    { url: "/api/tasks/12/declaration-documents/invoice/prepare", body: {} },
    {
      url: "/api/tasks/signed-contracts/upload-jobs",
      body: { requestId: "test-request", files: [{ filename: "SUB-200.pdf", size: 200000 }] },
    },
  ]);
});
