import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { matchRoutes, MemoryRouter } from "react-router";
import { createServer } from "vite";

let server, navigation, identityRoutes, LoginPage, SessionContext;
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
  ({ SessionContext } = await server.ssrLoadModule("/src/modules/identity/session-context.ts"));
});
after(async () => {
  await server?.close();
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
    assert.equal(navigation.getLoginDestination(state), "/pl-reconciliation");
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
    assert.equal(navigation.getLoginDestination({ from: value }), "/pl-reconciliation", value);
  }
});

test("登录表单保留标签、密码自动填充与后端错误，提交中禁用控件", () => {
  const markup = render({ error: "用户名或密码错误", busy: true });
  assert.match(markup, /for="identity-username">用户名<\/label>/);
  assert.match(markup, /for="identity-password">密码<\/label>/);
  assert.match(markup, /autoComplete="current-password"/);
  assert.match(markup, /role="alert">用户名或密码错误/);
  assert.match(markup, /正在登录/);
  assert.match(markup, /aria-label="显示密码"/);
  assert.match(markup, /aria-controls="identity-password"/);
  assert.equal((markup.match(/disabled=""/g) ?? []).length, 4);
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
