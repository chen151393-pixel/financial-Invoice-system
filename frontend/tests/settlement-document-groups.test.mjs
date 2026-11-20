import assert from "node:assert/strict";
import { before, after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { createServer } from "vite";

let server;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
});
after(() => server?.close());
test("资料组创建只提交报关单和幂等标识，不接收或计算金额", async (t) => {
  const { createDocumentGroup } = await server.ssrLoadModule(
    "/src/modules/settlement/api/document-group-api.ts",
  );
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "/api/settlement/direct-document-groups");
    assert.deepEqual(JSON.parse(options.body), { requestId: "test-request", declarationNos: ["D1", "D2"] });
    return Response.json({ id: 42 });
  });
  assert.deepEqual(await createDocumentGroup("test-request", ["D1", "D2"]), { id: 42 });
});
test("资料组的提单和合同使用独立命名空间", async (t) => {
  const { getDocuments, generateContracts } = await server.ssrLoadModule("/src/modules/settlement/api.ts");
  const seen = [];
  t.mock.method(globalThis, "fetch", async (url) => {
    seen.push(url);
    return Response.json({});
  });
  await getDocuments({ groupId: 42 });
  await generateContracts(
    { groupId: 42 },
    { tradeTerm: "FOB", paymentTermsCn: "预付", paymentTermsEn: "advance" },
  );
  assert.deepEqual(seen, [
    "/api/settlement/direct-document-groups/42/documents",
    "/api/settlement/direct-document-groups/42/contracts/generate",
  ]);
});
test("同号合同的预览保留两个卖方与各自报关单，不提供手选卖方", async () => {
  const { ContractGenerateForm } = await server.ssrLoadModule(
    "/src/modules/settlement/components/ContractGenerateForm.tsx",
  );
  const documents = {
    defaults: { tradeTerm: "FOB", paymentTermsCn: "预付", paymentTermsEn: "advance" },
    planned: [
      {
        key: "seller-a",
        contractNo: "SO-1",
        buyerName: "ACME LTD",
        sellerName: "出口抬头甲",
        declarationNos: ["D1"],
      },
      {
        key: "seller-b",
        contractNo: "SO-1",
        buyerName: "ACME LTD",
        sellerName: "出口抬头乙",
        declarationNos: ["D2"],
      },
    ],
  };
  const html = renderToStaticMarkup(
    createElement(
      MemoryRouter,
      null,
      createElement(ContractGenerateForm, { documents, busy: false, onCancel() {}, onSubmit() {} }),
    ),
  );
  assert.match(html, /出口抬头甲/);
  assert.match(html, /出口抬头乙/);
  assert.match(html, /D1/);
  assert.match(html, /D2/);
  assert.doesNotMatch(html, /name="sellerPartyId"/);
  assert.match(html, /销售订单 \/ 对应报关单/);
  assert.doesNotMatch(html, /出口合同号/);
  const { directDocumentGroupPath } = await server.ssrLoadModule("/src/app/paths.ts");
  assert.equal(directDocumentGroupPath(42), "/settlement/direct/document-groups/42");
});

test("单票自动建组只提交报关单，合并提交后端预览标识", async (t) => {
  const { ensureSingleDocumentGroup } = await server.ssrLoadModule(
    "/src/modules/settlement/api/document-group-api.ts",
  );
  const { previewDocumentMerge, confirmDocumentMerge } = await server.ssrLoadModule(
    "/src/modules/settlement/api/document-merge-api.ts",
  );
  const bodies = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    bodies.push([url, JSON.parse(options.body)]);
    return Response.json({ id: 42 });
  });
  await ensureSingleDocumentGroup("D1");
  const selection = { sourceDeclarationNo: "D1", declarationNos: ["D1", "D2"], sharedBillId: 8 };
  await previewDocumentMerge(selection);
  const confirmation = { ...selection, requestId: "same-request", previewToken: "a".repeat(64) };
  await confirmDocumentMerge(confirmation);
  assert.deepEqual(bodies, [
    ["/api/settlement/direct-document-groups/single", { declarationNo: "D1" }],
    ["/api/settlement/direct-document-groups/merge/preview", selection],
    ["/api/settlement/direct-document-groups/merge", confirmation],
  ]);
  assert.ok(bodies.every(([, body]) => !("amount" in body)));
});
test("直接收汇只有一排工作区切换，旧单票链接仍可进入资料组", async () => {
  const { SettlementLedgerPage } = await server.ssrLoadModule(
    "/src/modules/settlement/pages/SettlementLedgerPage.tsx",
  );
  const html = renderToStaticMarkup(
    createElement(
      MemoryRouter,
      { initialEntries: ["/settlement/direct?tab=documents"] },
      createElement(SettlementLedgerPage),
    ),
  );
  assert.match(html, /客户总账/);
  assert.match(html, /报关资料/);
  assert.match(html, /多票资料组/);
  assert.doesNotMatch(html, /直接收汇资料查看方式/);
  const { directDocumentMergePath } = await server.ssrLoadModule("/src/app/paths.ts");
  assert.equal(
    new URL(directDocumentMergePath("TEST/001 中文"), "http://localhost").searchParams.get("declarationNo"),
    "TEST/001 中文",
  );
});

test("合并响应丢失时查询原请求并恢复已提交结果", async (t) => {
  const { confirmDocumentMergeRecovering } = await server.ssrLoadModule(
    "/src/modules/settlement/api/document-merge-api.ts",
  );
  const body = {
    sourceDeclarationNo: "D1",
    declarationNos: ["D1", "D2"],
    sharedBillId: 0,
    requestId: "original-request",
    previewToken: "a".repeat(64),
  };
  const seen = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    seen.push([url, options]);
    if (url.endsWith("/merge")) throw new TypeError("connection lost");
    return Response.json({ group: { id: 42 } });
  });
  assert.deepEqual(await confirmDocumentMergeRecovering(body), { id: 42 });
  assert.equal(seen[1][0], "/api/settlement/direct-document-groups/merge/requests/original-request");
  assert.deepEqual(JSON.parse(seen[0][1].body), body);
});

test("结果未明时按原请求重试，不生成新幂等号或替换所选范围", async (t) => {
  const { confirmDocumentMergeRecovering, MergeResultUnknown } = await server.ssrLoadModule(
    "/src/modules/settlement/api/document-merge-api.ts",
  );
  const body = {
    sourceDeclarationNo: "D1",
    declarationNos: ["D1", "D2"],
    sharedBillId: 0,
    requestId: "same-id",
    previewToken: "a".repeat(64),
  };
  const posted = [];
  let calls = 0;
  t.mock.method(globalThis, "fetch", async (url, options) => {
    if (url.endsWith("/merge")) {
      posted.push(JSON.parse(options.body));
      if (calls++ === 0) throw new TypeError("lost");
      return Response.json({ id: 42 });
    }
    return Response.json({ group: null });
  });
  await assert.rejects(confirmDocumentMergeRecovering(body), MergeResultUnknown);
  assert.deepEqual(await confirmDocumentMergeRecovering(body), { id: 42 });
  assert.deepEqual(posted, [body, body]);
});

test("合并结果查询失败保留未知状态，明确校验失败不冒充结果未知", async (t) => {
  const { confirmDocumentMergeRecovering, MergeResultUnknown } = await server.ssrLoadModule(
    "/src/modules/settlement/api/document-merge-api.ts",
  );
  const body = { requestId: "r" };
  let seen = 0;
  t.mock.method(globalThis, "fetch", async () => {
    seen++;
    throw new TypeError("offline");
  });
  await assert.rejects(confirmDocumentMergeRecovering(body), MergeResultUnknown);
  assert.equal(seen, 2);
  seen = 0;
  globalThis.fetch = async () => {
    seen++;
    return Response.json({ error: "预览过期" }, { status: 409 });
  };
  await assert.rejects(confirmDocumentMergeRecovering(body), (error) => error.status === 409);
  assert.equal(seen, 1);
});

test("来源确认仅提交后端预览摘要，不提交客户币种金额", async (t) => {
  const { confirmGroupBasis } = await server.ssrLoadModule(
    "/src/modules/settlement/api/document-group-api.ts",
  );
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "/api/settlement/direct-document-groups/42/source");
    assert.deepEqual(JSON.parse(options.body), { token: "b".repeat(64) });
    return Response.json({ id: 42 });
  });
  assert.deepEqual(await confirmGroupBasis(42, "b".repeat(64)), { id: 42 });
});
