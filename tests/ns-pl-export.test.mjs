import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../SuiteScripts/pl_lookup/pl_client.js", import.meta.url), "utf8");
const excelResponse = () =>
  new Response(new Uint8Array([80, 75, 3, 4, 1]), {
    headers: { "Content-Type": "application/zip" },
  });
function harness(
  fetch = async () => excelResponse(),
  target = "/app/site/hosting/scriptlet.nl?script=1&deploy=1&action=export&requestid=req-1",
) {
  const calls = {
    requests: [],
    messages: [],
    downloads: [],
    navigations: [],
    removed: 0,
    revoked: [],
    logs: [],
  };
  const timers = new Map();
  let timerId = 0;
  let client;
  class TestURL extends URL {
    static createObjectURL() {
      return "blob:test-file";
    }
    static revokeObjectURL(value) {
      calls.revoked.push(value);
    }
  }
  const window = {
    AbortController,
    URL: TestURL,
    location: {
      href: "https://example.test/app/site/hosting/scriptlet.nl",
      origin: "https://example.test",
      assign: (v) => calls.navigations.push(v),
    },
    open: (v) => calls.navigations.push(v),
    fetch: (url, options) => {
      calls.requests.push({ url, options });
      return fetch(url, options);
    },
    setTimeout: (fn, ms) => {
      const id = ++timerId;
      timers.set(id, { fn, ms });
      return id;
    },
    clearTimeout: (id) => timers.delete(id),
    document: {
      querySelector: () => null,
      body: { appendChild() {} },
      createElement: (tag) => {
        assert.equal(tag, "a");
        const anchor = {
          click: () => calls.downloads.push({ href: anchor.href, name: anchor.download }),
          remove: () => calls.removed++,
        };
        return anchor;
      },
    },
  };
  const dependencies = {
    "N/currentRecord": {
      get: () => ({ getValue: ({ fieldId }) => (fieldId === "custpage_export_url" ? target : "") }),
    },
    "N/ui/message": {
      Type: { INFORMATION: "info", ERROR: "error" },
      create: (options) => {
        const notice = {
          ...options,
          shown: false,
          hidden: false,
          show() {
            this.shown = true;
          },
          hide() {
            this.hidden = true;
          },
        };
        calls.messages.push(notice);
        return notice;
      },
    },
  };
  vm.runInNewContext(source, {
    define: (names, factory) => {
      client = factory(...names.map((key) => dependencies[key]));
    },
    window,
    console: { warn: (...args) => calls.logs.push(args), info() {} },
  });
  return { client, calls, timers, window };
}

test("创建日期变更自动选择CD查询，清空或其他字段变更不覆盖手动方式", () => {
  const h = harness();
  const mode = { value: "pl" };
  const listeners = [];
  const panel = {
    dataset: {},
    querySelector: () => mode,
    addEventListener: (event, handler) => {
      assert.equal(event, "change");
      listeners.push(handler);
    },
  };
  h.window.document.querySelector = (selector) => {
    assert.equal(selector, ".pl-query-panel");
    return panel;
  };
  h.client.pageInit();
  h.client.pageInit();
  assert.equal(listeners.length, 1);
  for (const name of ["custpage_created_from", "custpage_created_to"]) {
    mode.value = "declaration";
    listeners[0]({ target: { name, value: "2026-09-01" } });
    assert.equal(mode.value, "customsRecord");
    mode.value = "pl";
    listeners[0]({ target: { name, value: "" } });
    assert.equal(mode.value, "pl");
  }
  listeners[0]({ target: { name: "custpage_month", value: "2026-09" } });
  assert.equal(mode.value, "pl");
});

test("Excel下载在当前页完成，带原快照ID且不打开或跳转页面", async () => {
  const h = harness();
  await h.client.exportExcel();
  assert.equal(h.calls.requests.length, 1);
  const request = h.calls.requests[0];
  const url = new URL(request.url);
  assert.equal(url.searchParams.get("requestid"), "req-1");
  assert.equal(url.searchParams.get("custparam_download"), "1");
  assert.equal(request.options.credentials, "same-origin");
  assert.deepEqual(h.calls.navigations, []);
  assert.deepEqual(h.calls.downloads, [{ href: "blob:test-file", name: "PL_lookup_req-1.xlsx" }]);
  assert.equal(h.calls.removed, 1);
  assert.equal(h.calls.messages.at(-1).hidden, true);
  assert.equal(
    [...h.timers.values()].some((t) => t.ms === 60000),
    false,
  );
  [...h.timers.values()].find((t) => t.ms === 1000).fn();
  assert.deepEqual(h.calls.revoked, ["blob:test-file"]);
});

test("缓存失效及生成失败在原页提示，失败后可以重试，不下载错误JSON", async () => {
  for (const [code, expected] of [
    ["SNAPSHOT_UNAVAILABLE", /实时查询/],
    ["EXCEL_EXPORT_FAILED", /文件生成失败/],
  ]) {
    let attempts = 0;
    const h = harness(async () =>
      ++attempts === 1 ? Response.json({ code, diagnostic: { rule: "SNAPSHOT_EXPIRED" } }) : excelResponse(),
    );
    await h.client.exportExcel();
    assert.match(h.calls.messages.at(-1).message, expected);
    assert.equal(h.calls.messages.at(-1).type, "error");
    assert.equal(h.calls.downloads.length, 0);
    await h.client.exportExcel();
    assert.equal(h.calls.downloads.length, 1);
    assert.deepEqual(h.calls.navigations, []);
  }
});

test("登录HTML、服务端错误、伪装为附件的HTML及断网不会下载成Excel", async () => {
  for (const fetch of [
    async () => new Response("login", { headers: { "Content-Type": "text/html" } }),
    async () => new Response("failed", { status: 500 }),
    async () =>
      new Response("<html>login</html>", { headers: { "Content-Type": "application/octet-stream" } }),
    async () => {
      throw new Error("private network detail");
    },
  ]) {
    const h = harness(fetch);
    await h.client.exportExcel();
    assert.equal(h.calls.downloads.length, 0);
    assert.deepEqual(h.calls.navigations, []);
    assert.match(h.calls.messages.at(-1).message, /网络或登录状态/);
    assert.doesNotMatch(h.calls.messages.at(-1).message, /private network detail/);
  }
});

test("导出期间阻止重复请求，超时恢复按钮行为", async () => {
  const h = harness(
    (url, options) =>
      new Promise((resolve, reject) => {
        options.signal.addEventListener("abort", () => reject(new Error("abort")));
      }),
  );
  const pending = h.client.exportExcel();
  await h.client.exportExcel();
  assert.equal(h.calls.requests.length, 1);
  [...h.timers.values()].find((t) => t.ms === 60000).fn();
  await pending;
  const retried = h.client.exportExcel();
  assert.equal(h.calls.requests.length, 2);
  [...h.timers.values()].find((t) => t.ms === 60000).fn();
  await retried;
  assert.deepEqual(h.calls.navigations, []);
});

test("没有导出地址或地址跨域时不发送请求", async () => {
  for (const target of ["", "https://other.example/export"]) {
    const h = harness(undefined, target);
    await h.client.exportExcel();
    assert.equal(h.calls.requests.length, 0);
    assert.equal(h.calls.downloads.length, 0);
    assert.deepEqual(h.calls.navigations, []);
  }
});
