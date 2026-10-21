import assert from "node:assert/strict";
import { before, after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

let server, api, http, runWait, PullProgress, PullResults;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  ({ PullResults } = await server.ssrLoadModule("/src/modules/sync/PullResults.tsx"));
  api = await server.ssrLoadModule("/src/modules/sync/api.ts");
  http = await server.ssrLoadModule("/src/shared/api/http.ts");
  runWait = await server.ssrLoadModule("/src/modules/sync/run-wait.ts");
  ({ PullProgress } = await server.ssrLoadModule("/src/modules/sync/PullProgress.tsx"));
});
after(async () => {
  await server?.close();
});

const REQUEST = "0f8fad5b-d9cb-469f-a165-70867728950e";
const range = { startDate: "2026-09-01", endDate: "2026-09-30" };
const running = (progress = null) => ({
  requestId: REQUEST,
  kind: "customs-declarations",
  request: { offset: 20, limit: 20, ...range },
  status: "running",
  statusLabel: "执行中",
  progress,
  result: null,
  error: null,
});
const finished = (status, result = { count: 1, batch: { status } }) => ({
  ...running(),
  status,
  statusLabel: status,
  result,
});
const noWait = async () => {};

test("后台批次提交携带请求编号与日期，查询按原编号", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, ...options });
    return Response.json(running());
  });
  await api.startRun("customs-declarations", REQUEST, 20, range);
  await api.getRun(REQUEST);
  assert.equal(calls[0].url, "/api/sync/ns/runs");
  assert.equal(calls[0].headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(calls[0].body), {
    requestId: REQUEST,
    kind: "customs-declarations",
    offset: 20,
    limit: 20,
    requireDateRange: true,
    ...range,
  });
  assert.equal(calls[1].url, `/api/sync/ns/runs/${REQUEST}`);
});

test("只读和后台保存均将范围游标原样发送给后端", async (t) => {
  const bodies = [];
  const cursor = { afterId: "9007199254740993", throughId: null, offset: 0 };
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    bodies.push(JSON.parse(options.body));
    return Response.json(running());
  });
  await api.pullRecords("customs-declarations", 20000, range, cursor);
  await api.startRun("customs-declarations", REQUEST, 20000, range, cursor);
  assert.equal(bodies.length, 2);
  for (const body of bodies) {
    assert.deepEqual(body.cursor, cursor);
    assert.equal(body.offset, 20000);
    assert.equal(body.startDate, range.startDate);
    assert.equal(body.endDate, range.endDate);
  }
});

test("提交连接中断只按原编号查询，不重新提交并返回实际结果", async () => {
  let submits = 0;
  const reads = [running({ state: "running", label: "整页读取", completed: 1, total: 3, elapsedSeconds: 2 })];
  reads.push(finished("partial"));
  const shown = [];
  let unavailable = 0;
  const page = await runWait.waitForRun({
    submit: async () => {
      submits++;
      throw new Error("无法连接服务或连接已中断");
    },
    read: async () => reads.shift(),
    onRun: (run) => shown.push(run.status),
    onUnavailable: () => unavailable++,
    isCurrent: () => true,
    wait: noWait,
  });
  assert.equal(submits, 1);
  assert.equal(unavailable, 1);
  assert.deepEqual(shown, ["running", "partial"]);
  assert.equal(page.batch.status, "partial");
});

test("代理超时（5xx）后查询失败继续查询，后端给出结果前不判定失败", async () => {
  const errors = [
    new http.HttpError("后端服务暂时不可用", 504),
    new http.HttpError("后端服务暂时不可用", 502),
  ];
  const page = await runWait.waitForRun({
    submit: async () => {
      throw errors[0];
    },
    read: async () => {
      if (errors.length > 1) throw errors.pop();
      return finished("completed");
    },
    onRun: () => {},
    onUnavailable: () => {},
    isCurrent: () => true,
    wait: noWait,
  });
  assert.equal(page.batch.status, "completed");
});

test("后端明确拒绝时直接显示原因；多次查不到才判定未发起", async () => {
  await assert.rejects(
    runWait.waitForRun({
      submit: async () => {
        throw new http.HttpError("同一请求编号不能用于不同分页条件", 409);
      },
      read: async () => assert.fail("明确拒绝不查询"),
      onRun: () => {},
      onUnavailable: () => {},
      isCurrent: () => true,
      wait: noWait,
    }),
    /不同分页条件/,
  );
  let reads = 0;
  await assert.rejects(
    runWait.waitForRun({
      submit: async () => {
        throw new Error("连接中断");
      },
      read: async () => {
        reads++;
        throw new http.HttpError("未找到该同步批次", 404);
      },
      onRun: () => {},
      onUnavailable: () => {},
      isCurrent: () => true,
      wait: noWait,
    }),
    /未开始执行/,
  );
  assert.equal(reads, 3);
});

test("待核实和未写入给出后端原因，不当作保存成功", async () => {
  const unknown = { ...finished("unknown", null), statusLabel: "结果待核实", error: "数据库连接中断" };
  assert.throws(() => runWait.settleRun(unknown), /结果待核实（数据库连接中断）/);
  assert.throws(
    () => runWait.settleRun({ ...finished("failed", null), statusLabel: "本批未写入任何单据" }),
    /未写入/,
  );
  assert.equal(runWait.settleRun(finished("interrupted")).batch.status, "interrupted");
});

test("离开页面后停止查询，不再更新结果", async () => {
  let current = true;
  let reads = 0;
  await assert.rejects(
    runWait.waitForRun({
      submit: async () => running(),
      read: async () => {
        reads++;
        return running();
      },
      onRun: () => {
        current = false;
      },
      onUnavailable: () => {},
      isCurrent: () => current,
      wait: noWait,
    }),
    /已离开本批查询/,
  );
  assert.equal(reads, 0);
});

test("进度显示真实阶段与请求编号，不虚构整体百分比", () => {
  const progress = { state: "running", label: "读取报关明细", completed: 12, total: 40, elapsedSeconds: 8 };
  const render = (run, unavailable = false) =>
    renderToStaticMarkup(createElement(PullProgress, { run, unavailable }));
  const html = render(running(progress));
  assert.match(html, /role="status"/);
  assert.match(html, /读取报关明细（12 \/ 40）/);
  assert.match(html, /已用时 8 秒/);
  assert.match(html, new RegExp(REQUEST));
  assert.doesNotMatch(html, /%/);
  assert.match(render(running()), /等待后台开始执行/);
  assert.match(render(running(), true), /请勿重复提交/);
  assert.equal(render(null), "");
});

test("逐单结果展示成功和失败，无成功时不伪造保存时间", () => {
  const result = {
    count: 2,
    pulledAt: "2026-10-16T01:00:00Z",
    message: "部分保存",
    dateRange: { label: "创建日期", startDate: "2026-09-01", endDate: "2026-09-30" },
    rows: [],
    storage: {
      savedAt: null,
      purchase: { created: 0, updated: 0, linesCreated: 0, linesUpdated: 0 },
      customs: { created: 0, updated: 0, linesCreated: 0, linesUpdated: 0 },
    },
    batch: {
      status: "partial",
      canContinue: true,
      counts: { saved: 1, failed: 1, unknown: 0, not_processed: 0 },
      items: [
        { id: "1", number: "SUB-001", status: "saved", reason: "已提交" },
        { id: "2", number: "SUB-002", status: "failed", reason: "单价格式不合规" },
      ],
    },
  };
  const html = renderToStaticMarkup(createElement(PullResults, { result }));
  assert.match(html, /SUB-001/);
  assert.match(html, /SUB-002/);
  assert.match(html, /失败，未保存/);
  assert.match(html, /单价格式不合规/);
  assert.match(html, /本批暂无确认成功的保存记录/);
  assert.doesNotMatch(html, /Invalid Date|1970/);
});
