import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { matchRoutes, MemoryRouter } from "react-router";
import { createServer } from "vite";

let server, navigation, identityRoutes, LoginPage, PasswordLoginForm, SessionContext, ImportedDirectory;
let RolePageForm, RequirePage, WorkspaceFrame, menu, pagePaths, identityApi;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  navigation = await server.ssrLoadModule("/src/modules/identity/login-navigation.ts");
  ({ identityRoutes } = await server.ssrLoadModule("/src/modules/identity/routes.tsx"));
  ({ LoginPage } = await server.ssrLoadModule("/src/modules/identity/pages/LoginPage.tsx"));
  ({ PasswordLoginForm } = await server.ssrLoadModule(
    "/src/modules/identity/components/PasswordLoginForm.tsx",
  ));
  ({ SessionContext } = await server.ssrLoadModule("/src/modules/identity/session-context.ts"));
  ({ ImportedDirectory } = await server.ssrLoadModule(
    "/src/modules/identity/components/ImportedDirectory.tsx",
  ));
  ({ RolePageForm } = await server.ssrLoadModule("/src/modules/identity/components/RolePageForm.tsx"));
  ({ RequirePage } = await server.ssrLoadModule("/src/modules/identity/RequirePage.tsx"));
  ({ AppFrame: WorkspaceFrame } = await server.ssrLoadModule("/src/app/WorkspaceFrame.tsx"));
  ({ navigation: menu } = await server.ssrLoadModule("/src/app/navigation.tsx"));
  pagePaths = await server.ssrLoadModule("/src/app/paths.ts");
  identityApi = await server.ssrLoadModule("/src/modules/identity/api.ts");
});
after(async () => {
  await server?.close();
});

test("旧后端缺少部门筛选字段时保留部门导航并明确提示，不冒充空部门", () => {
  const departments = [{ id: 1, openDepartmentId: "finance", name: "财务部", path: "财务部", roles: [] }];
  const markup = renderToStaticMarkup(
    createElement(
      MemoryRouter,
      null,
      createElement(ImportedDirectory, {
        data: { departments, roles: [] },
        department: "finance",
        onSelect() {},
        onSaved: async () => {},
      }),
    ),
  );
  assert.match(markup, /财务部/);
  assert.match(markup, /后端版本尚未更新/);
  assert.match(markup, /财务部 · 已导入员工/);
});

test("新后端明确返回空部门列表时不退回完整部门，也不提示版本错误", () => {
  const departments = [
    { id: 1, openDepartmentId: "empty", name: "未导入部门", path: "未导入部门", roles: [] },
  ];
  const markup = renderToStaticMarkup(
    createElement(
      MemoryRouter,
      null,
      createElement(ImportedDirectory, {
        data: { departments, importedDepartments: [], roles: [] },
        department: "",
        onSelect() {},
        onSaved: async () => {},
      }),
    ),
  );
  assert.doesNotMatch(markup, /未导入部门|后端版本尚未更新/);
  assert.match(markup, /全部已导入员工/);
});

const render = (overrides = {}) =>
  renderToStaticMarkup(
    createElement(
      MemoryRouter,
      { initialEntries: ["/login"] },
      createElement(
        SessionContext,
        {
          value: {
            phase: "login",
            busy: false,
            error: "",
            signIn: async () => {},
            signOut: async () => {},
            retry() {},
            ...overrides,
          },
        },
        createElement(LoginPage),
      ),
    ),
  );

test("登录页只注册在独立 /login 路由，任务详情不是登录页", () => {
  assert.equal(matchRoutes(identityRoutes, "/login")[0].route.path, "/login");
  assert.equal(matchRoutes(identityRoutes, "/tasks/1"), null);
});

test("原业务地址由路由状态保存，登录地址固定为 /login", () => {
  const destination = "/tasks/1?tab=history&keyword=合同#documents";
  assert.equal(identityRoutes[0].path, "/login");
  assert.equal(navigation.getLoginDestination({ from: destination }), destination);
  for (const state of [null, undefined, {}, { from: 1 }, "/tasks/1"]) {
    assert.equal(navigation.getLoginDestination(state), "/workbench");
  }
});

test("登录回跳拒绝外部地址、登录循环和无效地址", () => {
  const unsafe = [
    "",
    "https://evil.invalid/tasks",
    "//evil.invalid",
    "javascript:alert(1)",
    "/login",
    "/login?next=/login",
    "/LOGIN/",
    "/%6cogin",
    "/tasks/../login",
    "/%zz",
    "/\\evil.invalid",
    "/tasks/1\n",
  ];
  for (const value of unsafe) {
    assert.equal(navigation.getLoginDestination({ from: value }), "/workbench", value);
  }
});

test("应急登录表单保留标签、密码自动填充，提交中禁用控件", () => {
  const markup = renderToStaticMarkup(
    createElement(PasswordLoginForm, { busy: true, error: "用户名或密码错误", onSubmit() {} }),
  );
  assert.match(markup, /for="identity-username">用户名<\/label>/);
  assert.match(markup, /for="identity-password">密码<\/label>/);
  assert.match(markup, /autoComplete="current-password"/);
  assert.match(markup, /aria-describedby="identity-feedback"/);
  assert.match(markup, /正在登录/);
  assert.match(markup, /aria-label="显示密码"/);
  assert.match(markup, /aria-controls="identity-password"/);
  assert.equal((markup.match(/disabled=""/g) ?? []).length, 4);
});

test("登录页先读取后端登录方式，读取完成前不展示可提交表单，并显示后端错误", () => {
  const markup = render({ error: "用户名或密码错误" });
  assert.match(markup, /role="alert">用户名或密码错误/);
  assert.match(markup, /正在读取登录方式/);
  assert.doesNotMatch(markup, /<form/);
});

test("检查会话的加载与失败状态不展示可提交表单", () => {
  const loading = render({ phase: "loading" });
  assert.match(loading, /role="status"/);
  assert.doesNotMatch(loading, /<form/);
  const failed = render({ phase: "error", error: "无法连接服务" });
  assert.match(failed, /无法连接服务/);
  assert.match(failed, /重新检查会话/);
  assert.doesNotMatch(failed, /<form/);
});

const withUser = (pages, child) =>
  renderToStaticMarkup(
    createElement(
      MemoryRouter,
      null,
      createElement(
        SessionContext,
        {
          value: {
            phase: "ready",
            user: { name: "测试成员", kind: "feishu", roles: [], pages, canManageAccess: false },
            busy: false,
            error: "",
            signOut: async () => {},
          },
        },
        child,
      ),
    ),
  );

test("页面守卫信任后端页面列表，不因角色名称或缺失字段放行", () => {
  const child = createElement(RequirePage, { view: "finance" }, createElement("p", null, "受保护的财务数据"));
  assert.match(withUser(["finance"], child), /受保护的财务数据/);
  assert.doesNotMatch(withUser(["invoices"], child), /受保护的财务数据/);
  assert.doesNotMatch(withUser(undefined, child), /受保护的财务数据/);
  assert.equal(pagePaths.homePath(["pl"]), "/pl-reconciliation");
  assert.equal(pagePaths.homePath(["finance", "invoices"]), "/review");
  assert.equal(pagePaths.homePath([]), "/access-denied");
});

test("共用侧栏只展示授权页面并隐藏空分组，NS 回写归采购", () => {
  const markup = withUser(
    ["writeback"],
    createElement(WorkspaceFrame, {
      groups: menu,
      activeId: "writeback",
      onNavigate() {},
      title: "测试页面",
    }),
  );
  assert.match(markup, /NS 回写/);
  assert.match(markup, /app-sidebar__label">采购/);
  assert.doesNotMatch(markup, /app-sidebar__label">系统|财务核对|人员与权限/);
  assert.equal(menu.filter((group) => group.items.some((item) => item.id === "writeback"))[0].label, "采购");
});

test("角色权限表展示实际选中值，管理员锁定、空权限不伪装默认授权", () => {
  const pages = [
    { code: "finance", label: "财务核对", group: "财务", description: "核对来源", assignable: true },
    {
      code: "access",
      label: "人员与权限",
      group: "系统",
      description: "管理成员角色与页面权限",
      assignable: true,
    },
  ];
  const renderRole = (role) =>
    renderToStaticMarkup(
      createElement(RolePageForm, {
        role,
        pages,
        onSave: async () => role,
        onReload: async () => {},
        onBusy() {},
      }),
    );
  const editable = renderRole({ code: "finance", label: "财务专员", pages: [], revision: 2, editable: true });
  assert.match(editable, /此角色没有可访问页面/);
  assert.match(editable, /保存页面权限/);
  assert.equal((editable.match(/disabled=""/g) ?? []).length, 0);
  assert.doesNotMatch(editable, /checked=""/);
  const admin = renderRole({
    code: "admin",
    label: "系统管理员",
    pages: ["finance", "access"],
    revision: 0,
    editable: false,
  });
  assert.equal((admin.match(/disabled=""/g) ?? []).length, 2);
  assert.equal((admin.match(/checked=""/g) ?? []).length, 2);
  assert.doesNotMatch(admin, /保存页面权限/);
});

test("权限保存仅提交勾选、角色来源和后端版本，失败不会伪装成功", async (t) => {
  const requests = [];
  const mock = t.mock.method(globalThis, "fetch", async (url, options) => {
    requests.push({ url, body: JSON.parse(options.body) });
    return Response.json({ saved: true });
  });
  await identityApi.saveRolePages("finance", ["finance"], 3);
  await identityApi.saveUserAccess(5, ["purchaser"], false, true, "a".repeat(64));
  assert.deepEqual(requests[0], {
    url: "/api/identity/role-pages/finance",
    body: { pages: ["finance"], revision: 3 },
  });
  assert.deepEqual(requests[1].body, {
    roles: ["purchaser"],
    customRoles: false,
    enabled: true,
    version: "a".repeat(64),
  });
  mock.mock.mockImplementation(async () =>
    Response.json({ error: "权限已变化，请重新读取" }, { status: 409 }),
  );
  await assert.rejects(identityApi.saveRolePages("finance", [], 3), /权限已变化/);
});
