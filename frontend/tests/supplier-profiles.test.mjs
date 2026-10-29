import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { createServer } from "vite";
let server, api, Table, Picker, DirectoryStatus, navigation, paths, Search, pollDirectory;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  api = await server.ssrLoadModule("/src/modules/task/api/supplier-group.ts");
  ({ SupplierProfileSearch: Search } = await server.ssrLoadModule(
    "/src/modules/task/components/SupplierProfileSearch.tsx",
  ));
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
  ({ pollWecomDirectory: pollDirectory } = await server.ssrLoadModule(
    "/src/modules/task/components/pollWecomDirectory.ts",
  ));
  paths = await server.ssrLoadModule("/src/app/paths.ts");
});
after(async () => {
  await server?.close();
});

test("供应商查询拆分三个独立输入并保留批量值与隐藏标签", () => {
  const html = renderToStaticMarkup(
    createElement(
      MemoryRouter,
      null,
      createElement(Search, {
        query: {
          keyword: "",
          supplierName: "甲,乙",
          groupName: "采购群;开票群",
          owner: "张三",
          status: "all",
          page: 1,
          pageSize: 20,
        },
        busy: false,
        onSearch() {},
        onRefresh() {},
      }),
    ),
  );
  assert.equal((html.match(/type="search"/g) || []).length, 3);
  for (const label of ["供应商", "外部群", "群主"])
    assert.ok(html.includes(`<span class="ui-sr-only">${label}</span>`));
  assert.match(html, /value="甲,乙"/);
  assert.match(html, /value="采购群;开票群"/);
  assert.match(html, /清空/);
});

test("供应商组合条件原样传给新模块接口，由后端搜索", async () => {
  const previous = globalThis.fetch;
  const query = {
    keyword: "",
    supplierName: "甲,乙",
    groupName: "群一;群二",
    owner: "张三\n李四",
    status: "enabled",
    page: 2,
    pageSize: 10,
  };
  globalThis.fetch = async (url, options) => {
    assert.equal(url, "/api/task/supplier-groups/profiles/query");
    assert.deepEqual(JSON.parse(options.body), query);
    return new Response(JSON.stringify({ items: [], total: 0 }), { status: 200 });
  };
  try {
    await api.querySupplierProfiles(query);
  } finally {
    globalThis.fetch = previous;
  }
});

test("外部群预填当前供应商名称，初始待查询且不自动访问企微", () => {
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
  assert.match(html, /value="浙江洪皓工贸有限公司"/);
  assert.match(html, /placeholder="浙江洪皓工贸有限公司"/);
  assert.doesNotMatch(html, /留空按供应商名称匹配/);
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

test("首次同步显示真实阶段和进度，失败不显示为零个匹配群", () => {
  const render = (data) => renderToStaticMarkup(createElement(DirectoryStatus, { data }));
  const base = { directoryHasSnapshot: false, directoryRefreshing: true };
  assert.match(render({ ...base, directoryState: "queued" }), /等待开始/);
  const listing = render({ ...base, directoryState: "listing", directoryDiscovered: 100 });
  assert.match(listing, /已发现 100 个群，总数确认中/);
  assert.doesNotMatch(listing, /progressbar|0%/);
  const details = render({
    ...base,
    directoryState: "details",
    directoryCompleted: 24,
    directoryTotal: 100,
    directoryPercent: 24,
  });
  assert.match(details, /已处理 24 \/ 100 个群/);
  assert.match(details, /aria-valuenow="24"/);
  assert.match(details, /关闭页面后仍会继续同步/);
  const failed = render({
    directoryHasSnapshot: false,
    directoryState: "failed",
    directoryRefreshError: "网络中断",
  });
  assert.match(failed, /暂无可用目录/);
  assert.doesNotMatch(failed, /当前保留上次成功/);
});

test("目录轮询串行执行，只提交一次刷新并在完成后停止", async ({ mock }) => {
  mock.timers.enable({ apis: ["setTimeout"] });
  const calls = [],
    received = [];
  let resolve;
  const stop = pollDirectory(
    (query) => {
      calls.push(query);
      return new Promise((done) => {
        resolve = done;
      });
    },
    { supplierId: "32", keyword: "采购", page: 2, refresh: true },
    (data) => received.push(data),
    (error) => assert.fail(String(error)),
  );
  try {
    mock.timers.tick(10000);
    assert.equal(calls.length, 1); // 未响应时不叠加请求。
    resolve({ directoryRefreshing: true });
    await Promise.resolve();
    mock.timers.tick(1500);
    assert.equal(calls.length, 2);
    assert.deepEqual(calls[1], { supplierId: "32", keyword: "采购", page: 2, refresh: false });
    resolve({ directoryRefreshing: false });
    await Promise.resolve();
    mock.timers.tick(10000);
    assert.equal(calls.length, 2);
    assert.equal(received.length, 2);
  } finally {
    stop();
  }
});

test("关闭或切换查询取消请求，忽略旧结果；轮询失败停止等待人工重试", async ({ mock }) => {
  mock.timers.enable({ apis: ["setTimeout"] });
  let resolve,
    signal,
    calls = 0;
  const stop = pollDirectory(
    (_, incoming) => {
      calls += 1;
      signal = incoming;
      return new Promise((done) => {
        resolve = done;
      });
    },
    { supplierId: "32", keyword: "", page: 1, refresh: false },
    () => assert.fail("已取消的结果不能覆盖新查询"),
    () => assert.fail("取消不应显示错误"),
  );
  stop();
  assert.equal(signal.aborted, true);
  resolve({ directoryRefreshing: true });
  await Promise.resolve();
  mock.timers.tick(5000);
  assert.equal(calls, 1);
  let error;
  const stopFailed = pollDirectory(
    async () => {
      throw new Error("断网");
    },
    { supplierId: "32", keyword: "", page: 1, refresh: false },
    () => assert.fail("失败不能返回成功"),
    (reason) => {
      error = reason;
    },
  );
  await Promise.resolve();
  assert.equal(error.message, "断网");
  stopFailed();
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
