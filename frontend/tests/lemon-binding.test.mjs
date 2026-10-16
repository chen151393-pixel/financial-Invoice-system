import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

let server, identity, lemon, LemonBindingView;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  ({ LemonBindingView } = await server.ssrLoadModule("/src/modules/sync/LemonBindingView.tsx"));
  identity = await server.ssrLoadModule("/src/modules/identity/api.ts");
  lemon = await server.ssrLoadModule("/src/modules/sync/lemon-api.ts");
});
after(async () => {
  await server?.close();
});

test("公网已登录会话不重新请求本机登录", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url) => {
    calls.push(url);
    return Response.json({ authenticated: true });
  });
  await identity.openLocalSession();
  assert.deepEqual(calls, ["/api/session"]);
});

test("未登录和连接失败都不自动建立本机会话", async (t) => {
  const calls = [];
  const mock = t.mock.method(globalThis, "fetch", async (url) => {
    calls.push(url);
    return url === "/api/session"
      ? Response.json({ error: "请先登录" }, { status: 401 })
      : Response.json({ authenticated: true });
  });
  await assert.rejects(identity.openLocalSession(), /请先登录/);
  assert.deepEqual(calls, ["/api/session"]);
  calls.length = 0;
  mock.mock.mockImplementation(async (url) => {
    calls.push(url);
    throw new TypeError("network interrupted");
  });
  await assert.rejects(identity.openLocalSession(), /无法连接/);
  assert.deepEqual(calls, ["/api/session"]);
});

test("绑定失败只提交一次，不自动重放密码和授权请求", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, options });
    return Response.json({ error: "绑定结果未知，请先核实" }, { status: 502 });
  });
  await assert.rejects(lemon.confirmLemonBinding("test-password"), /先核实/);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/sync/lemon/binding/confirm");
  assert.equal(calls[0].options.credentials, "same-origin");
  assert.deepEqual(JSON.parse(calls[0].options.body), { password: "test-password" });
});

const binding = (overrides = {}) => ({
  phase: "unbound",
  message: "尚未绑定柠檬云账号",
  mobile: "",
  confirmationMobile: "",
  verifiedAt: null,
  redirectUri: "https://example.test/api/lemon/oauth/callback",
  begin: { allowed: true, reason: "尚未绑定柠檬云账号" },
  confirm: { allowed: false, reason: "尚未绑定柠檬云账号" },
  verify: { allowed: false, reason: "仅查询已有账号与当前应用的绑定关系" },
  sync: { allowed: false, reason: "发票 API 自动拉取尚未接入，请继续使用下方 Excel 导入" },
  ...overrides,
});
const renderBinding = (data, overrides = {}) =>
  renderToStaticMarkup(
    createElement(LemonBindingView, {
      data,
      mobile: "",
      password: "",
      busy: "",
      error: "",
      invalidCallback: false,
      setMobile() {},
      setPassword() {},
      run() {},
      refresh() {},
      ...overrides,
    }),
  );

test("配置缺失只提示一次原因，仍保留配置说明和发票导入入口", () => {
  const blocked = { allowed: false, reason: "请管理员配置柠檬云应用编号和密钥" };
  const html = renderBinding(binding({ begin: blocked, confirm: blocked, verify: blocked }));
  assert.equal(html.split(blocked.reason).length - 1, 1);
  assert.doesNotMatch(html, /<input|<form|核实已有绑定/);
  assert.match(html, /查看管理员配置说明/);
  assert.match(html, /href="#lemon-invoice-import"/);
});

test("可授权时收集手机号，收到回调后只展示确认账号与密码", () => {
  assert.match(renderBinding(binding()), /type="tel"/);
  const html = renderBinding(
    binding({
      phase: "awaiting_confirmation",
      confirmationMobile: "13800000000",
      confirm: { allowed: true, reason: "已收到授权" },
    }),
  );
  assert.match(html, /13800000000/);
  assert.match(html, /type="password"/);
  assert.doesNotMatch(html, /type="tel"/);
  assert.match(html, /确认绑定此账号/);
});

test("未知结果和已绑定都不显示重新绑定表单，只提供后端允许的核实操作", () => {
  for (const phase of ["unknown", "binding", "bound"]) {
    const html = renderBinding(
      binding({
        phase,
        message: "当前状态需查看",
        begin: { allowed: false, reason: "当前状态需查看" },
        verify: { allowed: true, reason: "查询当前绑定" },
      }),
    );
    assert.doesNotMatch(html, /<form|<input/);
    assert.match(html, /核实已有绑定/);
    assert.match(html, /自动拉取尚未接入/);
  }
});

test("加载、读取失败和无效回调不误报绑定成功，并保留刷新入口", () => {
  assert.match(renderBinding(null), /正在读取绑定配置/);
  const failure = renderBinding(null, { error: "读取绑定状态失败" });
  assert.match(failure, /role="alert"/);
  assert.match(failure, /刷新状态/);
  assert.doesNotMatch(failure, /<form|已绑定/);
  assert.match(renderBinding(binding(), { invalidCallback: true }), /本次回调无效/);
});

test("提交期间禁用重复提交、核实与刷新", () => {
  const html = renderBinding(
    binding({ confirm: { allowed: true, reason: "" }, verify: { allowed: true, reason: "" } }),
    { busy: "confirm" },
  );
  const buttons = html.match(/<button[^>]*>/g);
  assert.equal(buttons.length, 3);
  assert.ok(buttons.every((button) => button.includes('disabled=""')));
  assert.match(html, /正在确认绑定/);
});
