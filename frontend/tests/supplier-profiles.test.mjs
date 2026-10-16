import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
let server, api, Table, navigation, paths;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  api = await server.ssrLoadModule("/src/modules/task/api/supplier-group.ts");
  ({ SupplierProfilesTable: Table } = await server.ssrLoadModule(
    "/src/modules/task/components/SupplierProfilesTable.tsx",
  ));
  ({ navigation } = await server.ssrLoadModule("/src/app/navigation.tsx"));
  paths = await server.ssrLoadModule("/src/app/paths.ts");
});
after(async () => {
  await server?.close();
});
test("供应商档案有独立基础资料导航和旧入口兼容路径", () => {
  const section = navigation.find((item) => item.label === "基础资料");
  assert.equal(section.items.find((item) => item.id === "supplier-profiles").label, "供应商档案");
  assert.equal(paths.viewPath("supplier-profiles"), "/suppliers");
  assert.equal(paths.legacyPaths.taskSupplierGroups, "/tasks/supplier-groups");
});
test("未绑定供应商也展示维护入口，已绑定展示群与群主身份", () => {
  const html = renderToStaticMarkup(
    createElement(Table, {
      disabled: false,
      onEdit() {},
      items: [
        { supplierId: "1", supplierName: "未绑定公司", account: "prod", nsInternalId: "77", binding: null },
        {
          supplierId: "2",
          supplierName: "已绑定公司",
          account: "prod",
          nsInternalId: "78",
          binding: {
            groupName: "外部采购群",
            chatId: "wr_test",
            employee: "张女士",
            userid: "owner1",
            enabled: true,
            updatedAt: "2026-10-16T01:00:00Z",
          },
        },
      ],
    }),
  );
  for (const text of ["未绑定公司", "尚未绑定外部群", "外部采购群", "wr_test", "张女士", "owner1"])
    assert.ok(html.includes(text));
  assert.equal((html.match(/维护档案/g) || []).length, 2);
});
test("匹配仅提交供应商身份；保存失败不自动重放", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return url.endsWith("/save")
      ? Response.json({ error: "配置已被修改" }, { status: 409 })
      : Response.json({ items: [], total: 0 });
  });
  await api.matchWecomGroups({ supplierId: "1", keyword: "", page: 1, refresh: false });
  assert.equal(calls[0].url, "/api/tasks/supplier-groups/wecom/match");
  assert.equal(calls[0].body.supplierId, "1");
  await assert.rejects(
    api.saveSupplierGroup({ supplierId: "1", chatId: "wr_test", revision: 1, enabled: true }),
    /配置已被修改/,
  );
  assert.equal(calls.length, 2);
});
