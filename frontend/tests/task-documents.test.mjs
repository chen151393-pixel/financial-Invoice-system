import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

// 合成样本只用于组件验证，不连接真实 NS、共享盘或业务数据库。
let server, api, uploadApi, Declarations, Signed, Upload, Results, Dropzone, TaskDocuments, TaskReview;
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
  ({ SignedUploadResults: Results } = await server.ssrLoadModule(
    "/src/modules/task/components/SignedUploadResults.tsx",
  ));
  ({ FileDropzone: Dropzone } = await server.ssrLoadModule("/src/shared/components/ui/FileDropzone.tsx"));
  ({ TaskDocuments } = await server.ssrLoadModule("/src/modules/task/components/TaskDocuments.tsx"));
  ({ TaskReview } = await server.ssrLoadModule("/src/modules/task/components/TaskReview.tsx"));
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

function declarationGroups(docs) {
  const row = (type) => {
    const doc = docs.find((item) => item.type === type);
    return doc ? { ...doc, taskId: "7", recordNumber: "CD870" } : null;
  };
  return [
    {
      taskId: "7",
      recordNumber: "CD870",
      declarationNumber: "REAL870",
      customs: row("customs_declaration"),
      sales: row("sales_contract"),
      invoice: row("invoice"),
    },
  ];
}

test("报关资料按报关单展示状态，销售合同仅显示状态并继续隐藏下载入口", () => {
  const html = renderToStaticMarkup(
    createElement(Declarations, { groups: declarationGroups(documents), count: 1, busy: null, onRetry() {} }),
  );
  assert.match(html, /CD870_REAL870/);
  assert.match(html, /销售合同/);
  assert.doesNotMatch(html, /下载销售合同|已尝试 2 次|NS 中暂无/);
  assert.match(html, /aria-label="CD870 重新下载报关单"/);
  // 接口未配置：按钮禁用并写明原因，不冒充可下载
  assert.match(html, /<button[^>]*disabled=""[^>]*aria-label="CD870 下载发票"/);
  assert.match(html, /报关资料下载接口尚未配置/);
  assert.match(html, /下载失败不影响通知供应商/);
});

test("销售合同仅展示状态不影响其他资料的失败原因和重试按钮", () => {
  const html = renderToStaticMarkup(
    createElement(Declarations, {
      groups: declarationGroups([
        documents[1],
        {
          ...documents[2],
          status: "failed",
          statusLabel: "下载失败",
          attempts: 3,
          error: "发票下载失败，请稍后重试",
          retry: allowed,
        },
      ]),
      busy: null,
      onRetry() {},
    }),
  );
  assert.doesNotMatch(html, /下载销售合同|NS 中暂无/);
  assert.match(html, /失败原因：发票下载失败，请稍后重试/);
  assert.match(html, /已尝试 3 次/);
  assert.match(html, /aria-label="CD870 下载发票"[^>]*>重试下载/);
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
  assert.match(html, /SUB-200[\s\S]*已上传[\s\S]*user:admin/);
  assert.match(html, /SUB-201[\s\S]*尚未上传/);
  assert.match(html, /上传回签合同/);
  assert.match(html, /<details class="it-materials it-materials__signed"><summary>/);
});

test("资料准备集中展示子采购合同、报关资料与回签合同，保留各项操作", () => {
  const prep = {
    contractSummary: "1 / 2 已归档",
    contractsReady: false,
    declarationCount: 1,
    signedSummary: "2 份待补齐",
    signedPendingCount: 2,
    note: "请先归档全部合同",
  };
  const docs = [
    {
      orderId: "200",
      orderNumber: "SUB-200",
      taskId: "7",
      recordNumber: "CD870",
      declarationNumber: "REAL870",
      status: "failed",
      filename: "",
      error: "共享盘不可写",
      prepare: { allowed: false, reason: "请核对共享盘权限" },
    },
  ];
  const detail = {
    preparation: prep,
    documents: docs,
    declarationRows: declarationGroups(documents),
    signedContracts: [],
    reasons: [],
    sourceStatus: "current",
    sourceMessage: "来源已变化，须重新审核",
    compare: { allowed: false },
    reviewRows: [
      {
        taskId: "7",
        recordNumber: "CD870",
        declarationNumber: "REAL870",
        reviewRevision: 3,
        customsStatusLabel: "已通过",
        financeStatusLabel: "已通过",
        orderCount: 2,
      },
    ],
  };
  const html = renderToStaticMarkup(
    createElement(TaskDocuments, {
      detail,
      busy: null,
      onPrepare() {},
      onRetryDeclaration() {},
      onUploadSigned() {},
    }),
  );
  for (const value of ["1 / 2 已归档", "CD870", "共享盘不可写", "请核对共享盘权限"])
    assert.ok(html.includes(value), value);
  for (const value of [
    "报关资料清单",
    "报关单文件",
    "发票文件",
    "共 1 组",
    'aria-label="CD870 重新下载报关单"',
    'aria-label="CD870 下载发票"',
  ])
    assert.ok(html.includes(value), value);
  assert.match(html, /回签合同/);
  assert.match(html, /2 份待补齐/);
  assert.match(html, /<details class="it-materials it-materials__signed"><summary>/);
  assert.match(html, /<button[^>]*>上传回签合同<\/button>/);
  assert.ok(html.indexOf("报关资料清单") < html.indexOf("it-materials__signed"));
  assert.match(html, /<table/);
  assert.match(html, /disabled=""[^>]*>重试保存/);
  assert.match(html, /保存路径|暂无保存路径/);
  const contractTable = html.slice(html.indexOf("<table"), html.indexOf("</table>") + 8);
  assert.doesNotMatch(contractTable, /子采购单 \/ 合同文件|归档详情|归档时间|来源环境/);
  const saved = renderToStaticMarkup(
    createElement(TaskDocuments, {
      detail: {
        ...detail,
        documents: [
          {
            ...docs[0],
            status: "ready",
            archivePath: "/mnt/invoice-contracts/合同.pdf",
            filename: "不单独展示的文件名.pdf",
            archivedAt: "2026-10-23T01:00:00Z",
            environment: "test-account",
            nsId: "42",
            error: "",
          },
        ],
      },
      busy: null,
      onPrepare() {},
      onRetryDeclaration() {},
      onUploadSigned() {},
    }),
  );
  assert.match(saved, /\/mnt\/invoice-contracts\/合同.pdf/);
  assert.match(saved, /<strong>SUB-200<\/strong>/);
  const savedContractTable = saved.slice(saved.indexOf("<table"), saved.indexOf("</table>") + 8);
  assert.doesNotMatch(savedContractTable, /不单独展示的文件名|test-account|归档详情|归档时间|来源环境/);
  for (const overrides of [{ busy: "saving" }, { detail: { ...detail, sourceStatus: "superseded" } }]) {
    const blocked = renderToStaticMarkup(
      createElement(TaskDocuments, {
        detail,
        busy: null,
        onPrepare() {},
        onRetryDeclaration() {},
        onUploadSigned() {},
        ...overrides,
      }),
    );
    assert.match(blocked, /<button[^>]*disabled=""[^>]*>上传回签合同<\/button>/);
  }
  const review = renderToStaticMarkup(createElement(TaskReview, { detail }));
  for (const value of ["海关审核", "财务审核", "审核版本 3", "来源已变化，须重新审核", "REAL870", "2 张"])
    assert.ok(review.includes(value), value);
  assert.match(
    renderToStaticMarkup(createElement(TaskReview, { detail: { ...detail, reviewRows: [] } })),
    /审核依据待获取/,
  );
});

test("上传窗口说明格式、大小与不覆盖规则，未选择文件时不能提交", () => {
  const html = renderToStaticMarkup(createElement(Upload, { onClose() {} }));
  assert.match(html, /批量上传回签合同/);
  assert.match(html, /PDF、JPG、PNG/);
  assert.match(html, /不会覆盖/);
  assert.match(html, /100 MB/);
  assert.match(html, /后台队列/);
  assert.match(html, /<input type="file" multiple=""/);
  assert.match(html, /<button[^>]*disabled=""[^>]*>开始上传/);
  assert.match(html, /点击选择或拖入回签合同/);
  assert.match(html, /下次打开窗口将清空本次展示/);
  assert.doesNotMatch(html, /最近任务|暂无上传任务|正在读取上传任务/);
});

test("当前结果优先展示文件和状态，成功不再占用双进度条，路径默认折叠", () => {
  const job = {
    id: "private-batch-id",
    phase: "completed",
    total: 2,
    finished: 2,
    saved: 1,
    message: "已处理 2/2 个文件，已保存 1 个",
    uploadPercent: 100,
    progressPercent: 100,
    items: [
      {
        id: "1",
        filename: "SUB-200.pdf",
        status: "saved",
        reason: "已保存到共享盘",
        orderNumber: "SUB-200",
        archivePath: "\\\\share\\SUB-200.pdf",
        canRetry: false,
      },
      {
        id: "2",
        filename: "无单号.pdf",
        status: "unmatched",
        reason: "未找到子采购单号，请核对后重试",
        orderNumber: "",
        archivePath: null,
        canRetry: true,
      },
    ],
  };
  const html = renderToStaticMarkup(
    createElement(Results, {
      job,
      index: 0,
      busy: false,
      transfers: {},
      canResume: () => false,
      onRetry() {},
    }),
  );
  assert.match(html, /已处理 2\/2 个文件，已保存 1 个/);
  assert.match(html, /已保存/);
  assert.match(html, /未识别单号/);
  assert.match(html, /重新处理/);
  assert.match(html, /<details class="itd-upload__path"><summary>查看保存位置/);
  assert.match(html, /min-width:0/);
  assert.doesNotMatch(html, /文件传输进度|后台处理进度|private-batch-id/);
  const busy = renderToStaticMarkup(
    createElement(Results, {
      job,
      index: 0,
      busy: true,
      transfers: {},
      canResume: () => false,
      onRetry() {},
    }),
  );
  assert.match(busy, /disabled=""[^>]*>重新处理/);
});

test("拖入区有可键盘访问的多文件选择框，忙碌时禁用选择", () => {
  const html = renderToStaticMarkup(
    createElement(Dropzone, {
      label: "选择合同",
      hint: "支持多选",
      accept: ".pdf",
      multiple: true,
      disabled: true,
      onFiles() {},
    }),
  );
  assert.match(html, /type="file" multiple="" accept=".pdf" disabled=""/);
  assert.match(html, /aria-label="选择合同"/);
  assert.match(html, /data-disabled="true"/);
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
