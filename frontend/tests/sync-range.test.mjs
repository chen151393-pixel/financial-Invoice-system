import assert from "node:assert/strict";
import test from "node:test";
import { pullDateRange } from "../src/modules/sync/range-pull.ts";

const range = { startDate: "2026-09-01", endDate: "2026-09-30" };
const page = (offset, hasMore) => ({
  offset,
  hasMore,
  nextOffset: hasMore ? offset + 20 : null,
  nextCursor: hasMore ? { afterId: String(offset + 20), throughId: null, offset: 0 } : null,
  rows: [],
  count: 0,
});

for (const save of [false, true]) {
  test(`超过 1000 批仍传递服务端范围游标继续拉取：${save}`, async () => {
    let batches = 0;
    await pullDateRange({
      range,
      save,
      shouldStop: () => false,
      onPage: () => {},
      readPage: async (offset, dates, persist, cursor) => {
        assert.equal(persist, save);
        assert.deepEqual(dates, range);
        assert.deepEqual(cursor, { afterId: String(offset), throughId: null, offset: 0 });
        batches++;
        return {
          ...page(offset, offset < 20020),
          nextCursor: offset < 20020 ? { afterId: String(offset + 20), throughId: null, offset: 0 } : null,
        };
      },
    });
    assert.equal(batches, 1002);
  });
}

for (const save of [false, true]) {
  test(`自动拉取所有批次并保持日期和保存模式：${save}`, async () => {
    const calls = [],
      received = [];
    const outcome = await pullDateRange({
      range,
      save,
      shouldStop: () => false,
      readPage: async (offset, dates, persist) => {
        calls.push({ offset, dates, persist });
        return page(offset, offset < 40);
      },
      onPage: (value) => received.push(value),
    });
    assert.equal(outcome, "completed");
    assert.deepEqual(
      calls.map((call) => call.offset),
      [0, 20, 40],
    );
    assert.ok(
      calls.every(
        (call) =>
          call.persist === save &&
          call.dates.startDate === range.startDate &&
          call.dates.endDate === range.endDate,
      ),
    );
    assert.equal(received.length, 3);
  });
}

test("中途失败保留已完成批次且不自动重试", async () => {
  const calls = [],
    received = [];
  await assert.rejects(
    pullDateRange({
      range,
      save: true,
      shouldStop: () => false,
      readPage: async (offset) => {
        calls.push(offset);
        if (offset === 20) throw new Error("连接中断");
        return page(offset, true);
      },
      onPage: (value) => received.push(value),
    }),
    /连接中断/,
  );
  assert.deepEqual(calls, [0, 20]);
  assert.equal(received.length, 1);
});

test("停止等待当前保存响应，不发起下一批", async () => {
  let stop = false;
  const received = [],
    calls = [];
  const outcome = await pullDateRange({
    range,
    save: true,
    shouldStop: () => stop,
    readPage: async (offset) => {
      calls.push(offset);
      stop = true;
      return page(offset, true);
    },
    onPage: (value) => received.push(value),
  });
  assert.equal(outcome, "stopped");
  assert.deepEqual(calls, [0]);
  assert.equal(received.length, 1);
});

test("空时间段完成，且不会继续请求", async () => {
  let calls = 0;
  const outcome = await pullDateRange({
    range,
    save: false,
    shouldStop: () => false,
    readPage: async (offset) => {
      calls++;
      return page(offset, false);
    },
    onPage: () => {},
  });
  assert.equal(outcome, "completed");
  assert.equal(calls, 1);
});

test("异常分页游标停止，避免循环请求", async () => {
  await assert.rejects(
    pullDateRange({
      range,
      save: false,
      shouldStop: () => false,
      readPage: async () => ({ ...page(0, true), nextOffset: 0 }),
      onPage: () => {},
    }),
    /分页位置异常/,
  );
});

for (const nextCursor of [undefined, null, { afterId: "0", throughId: null, offset: 0 }]) {
  test(`缺失或未推进的范围游标停止，不退回全局偏移：${JSON.stringify(nextCursor)}`, async () => {
    let calls = 0;
    const received = [];
    await assert.rejects(
      pullDateRange({
        range,
        save: true,
        shouldStop: () => calls > 1,
        readPage: async () => {
          calls++;
          return { ...page(0, true), nextCursor };
        },
        onPage: (value) => received.push(value),
      }),
      /范围游标异常/,
    );
    assert.equal(calls, 1);
    assert.equal(received.length, 1);
  });
}

test("请求期间修改输入不改变已提交日期", async () => {
  const input = { ...range },
    observed = [];
  await pullDateRange({
    range: input,
    save: false,
    shouldStop: () => false,
    readPage: async (offset, dates) => {
      observed.push({ ...dates });
      input.endDate = "2026-10-16";
      return page(offset, offset === 0);
    },
    onPage: () => {},
  });
  assert.deepEqual(observed, [range, range]);
});

test("部分保存保留结果并继续下一批，最终不能标记全量成功", async () => {
  const calls = [],
    received = [];
  const outcome = await pullDateRange({
    range,
    save: true,
    shouldStop: () => false,
    readPage: async (offset) => {
      calls.push(offset);
      return {
        ...page(offset, offset === 0),
        batch: { status: offset === 0 ? "partial" : "completed", canContinue: true },
      };
    },
    onPage: (value) => received.push(value),
  });
  assert.equal(outcome, "partial");
  assert.deepEqual(calls, [0, 20]);
  assert.equal(received.length, 2);
});

test("提交结果待核实时先保留本批结果，再停止翻页且不重试", async () => {
  const calls = [],
    received = [];
  await assert.rejects(
    pullDateRange({
      range,
      save: true,
      shouldStop: () => false,
      readPage: async (offset) => {
        calls.push(offset);
        return {
          ...page(offset, true),
          message: "保存结果待核实",
          batch: { status: "interrupted", canContinue: false },
        };
      },
      onPage: (value) => received.push(value),
    }),
    /保存结果待核实/,
  );
  assert.deepEqual(calls, [0]);
  assert.equal(received.length, 1);
});
