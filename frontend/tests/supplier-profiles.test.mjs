import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
let server, api, Table, Picker, DirectoryStatus, navigation, paths;
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
  ({ WecomGroupPicker: Picker } = await server.ssrLoadModule(
    "/src/modules/task/components/WecomGroupPicker.tsx",
  ));
  ({ WecomDirectoryStatus: DirectoryStatus } = await server.ssrLoadModule(
    "/src/modules/task/components/WecomDirectoryStatus.tsx",
  ));
  paths = await server.ssrLoadModule("/src/app/paths.ts");
});
after(async () => {
  await server?.close();
});

test("外部群初始展示待查询，输入与查找可用，说明留空自动匹配", () => {
  const html = renderToStaticMarkup(
    createElement(Picker, {
      supplier: { supplierId: "32", supplierName: "浙江洪皓工贸有限公司" },
      search() {
        assert.fail("初始不应查询");
      },
      onChoose() {},
      disabled: false,
      inputRef: null,
    }),
  );
  assert.match(html, /尚未查询外部群/);
  assert.match(html, /输入框留空时，自动按“浙江洪皓工贸有限公司”匹配/);
  assert.doesNotMatch(html, /disabled|正在|没有匹配的外部群|重新拉取/);
});
test("供应商档案在采购分组导航中，并保留旧入口兼容路径", () => {
  const section = navigation.find((item) => item.label === "采购");
  assert.equal(section.items.find((item) => item.id === "supplier-profiles").label, "供应商档案");
  assert.equal(paths.viewPath("supplier-profiles"), "/suppliers");
  assert.equal(paths.legacyPaths.taskSupplierGroups, "/tasks/supplier-groups");
});

test("群目录缓存明确标注时间、后台更新和失败，不冒充最新结果", () => {
  const render = (data) => renderToStaticMarkup(createElement(DirectoryStatus, { data }));
  assert.equal(render({}), "");
  const data = { directoryUpdatedAt: "2026-10-20T01:00:00Z", directoryStale: true };
  assert.match(render({ ...data, directoryRefreshing: true }), /后台正在更新群目录/);
  assert.match(render(data), /可能不包含最近新增或改名的群/);
  assert.match(
    render({ ...data, directoryRefreshError: "企微网络不可用" }),
    /群目录更新失败：企微网络不可用/,
  );
  assert.match(render(data), /保存时会实时核验所选群与群主/);
});
test("未绑定供应商也展示维护入口，已绑定展示群与群主身份", () => {
  const html = renderToStaticMarkup(
    createElement(Table, {
      disabled: false,
      saving: null,
      onEdit() {},
      onNotify() {},
      items: [
        {
          supplierId: "1",
          supplierName: "未绑定公司",
          account: "prod",
          nsInternalId: "77",
          binding: null,
          notify: { enabled: true, revision: 0, updatedBy: "", updatedAt: null },
        },
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
          notify: { enabled: false, revision: 2, updatedBy: "user:admin", updatedAt: "2026-10-23T01:00:00Z" },
        },
      ],
    }),
  );
  // 未绑定外部群的供应商也能维护通知开关；关闭时用文字写明后果
  assert.match(html, /aria-label="关闭供应商通知：未绑定公司"/);
  assert.match(html, /aria-label="开启供应商通知：已绑定公司"/);
  assert.match(html, /已关闭 · 不生成开票任务/);
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

test("通知开关只提交供应商、开关与版本；冲突时给出后端原因", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return Response.json({ error: "供应商通知设置已被他人修改，请刷新后重试" }, { status: 409 });
  });
  await assert.rejects(api.saveSupplierNotify("7", false, 3), /已被他人修改/);
  assert.deepEqual(calls, [
    {
      url: "/api/tasks/supplier-groups/profiles/notify",
      body: { supplierId: "7", enabled: false, revision: 3 },
    },
  ]);
});
