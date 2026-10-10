import assert from "node:assert/strict";
import test from "node:test";
import { http, HttpError } from "../src/shared/api/http.ts";

test("明确的业务拒绝保留HTTP状态供表单恢复", async (t) => {
  t.mock.method(globalThis, "fetch", async () =>
    Response.json({ error: "请填写人工确认说明" }, { status: 422 }),
  );
  await assert.rejects(http("/matching/invoices/1/links", "POST", {}), (error) => {
    assert.ok(error instanceof HttpError);
    assert.equal(error.status, 422);
    assert.equal(error.message, "请填写人工确认说明");
    return true;
  });
});

test("公共请求正确处理代理和后端响应", async (t) => {
  const cases = [
    [500, "", /后端服务暂时不可用（HTTP 500）/],
    [502, "<html>private-proxy-error</html>", /HTTP 502/],
    [503, '{"error":"NS 配置不完整"}', /NS 配置不完整/],
    [401, '{"error":"请先登录"}', /请先登录/],
    [404, "", /HTTP 404/],
    [500, '{"error":""}', /HTTP 500/],
    [200, "", /数据为空或格式异常/],
    [200, "<html>private-page</html>", /数据为空或格式异常/],
    [200, "null", /数据为空或格式异常/],
  ];
  for (const [status, body, expected] of cases) {
    await t.test(`${status} ${body}`, async (t) => {
      let calls = 0;
      t.mock.method(globalThis, "fetch", async () => {
        calls += 1;
        return new Response(body, { status });
      });
      await assert.rejects(http("/session/local", "POST", {}), (error) => {
        assert.match(error.message, expected);
        assert.doesNotMatch(error.message, /private-|Unexpected|JSON input/);
        return true;
      });
      assert.equal(calls, 1);
    });
  }
});

test("正常响应保留数据与请求参数", async (t) => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "/api/session/local");
    assert.equal(options.method, "POST");
    assert.equal(options.credentials, "same-origin");
    assert.equal(options.body, "{}");
    return Response.json({ authenticated: true });
  });
  assert.deepEqual(await http("/session/local", "POST", {}), { authenticated: true });
});

test("网络错误显示中文，取消请求保留原异常", async (t) => {
  const mock = t.mock.method(globalThis, "fetch", async () => {
    throw new TypeError("Failed to fetch");
  });
  await assert.rejects(http("/session/local"), /无法连接服务或连接已中断/);
  const aborted = new DOMException("cancelled", "AbortError");
  mock.mock.mockImplementation(async () => {
    throw aborted;
  });
  await assert.rejects(http("/session/local"), (error) => error === aborted);
});

test("读取响应时断线也显示中文", async (t) => {
  t.mock.method(globalThis, "fetch", async () => ({
    text: async () => {
      throw new TypeError("terminated");
    },
  }));
  await assert.rejects(http("/session/local"), /无法连接服务或连接已中断/);
});
