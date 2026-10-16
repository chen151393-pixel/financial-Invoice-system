import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
let server, api, Rows, Picker, paths;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  api = await server.ssrLoadModule("/src/modules/task/api/external-group.ts");
  ({ GroupImportRows: Rows } = await server.ssrLoadModule(
    "/src/modules/task/components/GroupImportRows.tsx",
  ));
  ({ SupplierAssociation: Picker } = await server.ssrLoadModule(
    "/src/modules/task/components/SupplierAssociation.tsx",
  ));
  paths = await server.ssrLoadModule("/src/app/paths.ts");
});
after(async () => {
  await server?.close();
});
const supplier = { supplierId: "1", supplierName: "供应商甲", account: "prod", binding: null };
test("外部群预览有独立路由，错误行禁用关联，未匹配行仍可手动维护", () => {
  assert.equal(paths.paths.externalGroups, "/suppliers/external-groups");
  const html = renderToStaticMarkup(
    createElement(Rows, {
      choices: {},
      busy: false,
      editing: false,
      onEdit() {},
      onClear() {},
      data: {
        confirm: { allowed: true },
        items: [
          {
            rowNo: 2,
            groupName: "错误群",
            group: null,
            issue: "缺少群主 ID",
            candidates: [],
            candidateCount: 0,
          },
          {
            rowNo: 3,
            groupName: "简称采购群",
            group: { employee: "群主", userid: "owner", chatId: "wr_id" },
            issue: "",
            candidates: [],
            candidateCount: 0,
          },
        ],
      },
    }),
  );
  assert.ok(html.includes("缺少群主 ID"));
  assert.ok(html.includes("未匹配，请手动关联"));
  assert.equal((html.match(/disabled=""/g) || []).length, 1);
});
test("人工关联展示原群和替换确认，不隐式提交选择", () => {
  const html = renderToStaticMarkup(
    createElement(Picker, {
      groupName: "新群",
      candidates: [supplier],
      busy: false,
      initial: {
        supplier: { ...supplier, binding: { groupName: "原群", employee: "原群主", chatId: "old" } },
        replaceExisting: false,
      },
      onApply() {},
      onClose() {},
    }),
  );
  assert.ok(html.includes("原绑定："));
  assert.ok(html.includes("原群主"));
  assert.ok(html.includes("我确认用当前群替换"));
  assert.ok(html.includes("使用此关联"));
});
test("确认仅提交行号和供应商身份版本，失败不自动重放", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return Response.json({ error: "原绑定已更新" }, { status: 409 });
  });
  await assert.rejects(
    api.confirmGroups("preview-id", { 2: { supplier, replaceExisting: false } }),
    /原绑定已更新/,
  );
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].body, {
    importId: "preview-id",
    selections: [{ rowNo: 2, supplierId: "1", revision: 0, replaceExisting: false }],
  });
});

test("未提供群人数不会显示为零或 Invalid Date，真实零人数正常显示", async () => {
  const { ExternalGroupRows } = await server.ssrLoadModule(
    "/src/modules/task/components/ExternalGroupRows.tsx",
  );
  const html = renderToStaticMarkup(
    createElement(ExternalGroupRows, {
      data: {
        items: [
          { chatId: "wr_missing", groupName: "未获取群", memberCount: null, createdAt: "", suppliers: [] },
          { chatId: "wr_zero", groupName: "空群", memberCount: 0, createdAt: "", suppliers: [] },
        ],
      },
      disabled: false,
      onEdit() {},
    }),
  );
  assert.ok(html.includes("人数未提供"));
  assert.ok(html.includes("0 人"));
  assert.ok(!html.includes("null 人"));
  assert.ok(!html.includes("Invalid Date"));
});
