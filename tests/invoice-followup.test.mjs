import assert from "node:assert/strict";
import { test } from "node:test";
import { followupTasks, groupFollowupTasks } from "../app/demo/invoice-followup-data.ts";

test("供应商和报关单视图保留同一批任务，切换不合并或复制业务记录", () => {
  const expected = followupTasks.map((task) => task.id).sort();
  const snapshot = JSON.stringify(followupTasks);
  for (const groupBy of ["supplier", "declaration"]) {
    const groups = groupFollowupTasks(followupTasks, groupBy);
    assert.deepEqual(groups.flatMap((group) => group.tasks.map((task) => task.id)).sort(), expected);
    for (const task of groups.flatMap((group) => group.tasks)) {
      assert.equal(
        task,
        followupTasks.find((source) => source.id === task.id),
      );
    }
  }
  assert.equal(JSON.stringify(followupTasks), snapshot);
});

test("样本同时覆盖供应商跨报关单和报关单包含多个供应商", () => {
  const suppliers = groupFollowupTasks(followupTasks, "supplier");
  const declarations = groupFollowupTasks(followupTasks, "declaration");
  assert.equal(suppliers.length, 3);
  assert.equal(declarations.length, 5);
  const haichuan = suppliers.find((group) => group.key === "宁波海川五金有限公司");
  assert.equal(haichuan.relatedCount, 3);
  assert.deepEqual(
    haichuan.tasks.map((task) => task.id),
    ["KP-202609-001", "KP-202609-003", "KP-202609-006"],
  );
  assert.equal(declarations.find((group) => group.key === "CD-2609018").relatedCount, 2);
});

test("筛选后摘要只统计匹配任务，部分收票可以同时计入待开票和已收票", () => {
  const partial = followupTasks.filter((task) => task.id === "KP-202609-002");
  for (const groupBy of ["supplier", "declaration"]) {
    const [group] = groupFollowupTasks(partial, groupBy);
    assert.equal(group.awaitingCount, 1);
    assert.equal(group.receivedCount, 2);
    assert.equal(group.attentionCount, 0);
    assert.equal(group.tasks.length, 1);
  }
  const attention = followupTasks.filter((task) => task.category === "mine");
  const groups = groupFollowupTasks(attention, "supplier");
  assert.equal(
    groups.reduce((count, group) => count + group.attentionCount, 0),
    3,
  );
  assert.equal(
    groups.reduce((count, group) => count + group.receivedCount, 0),
    1,
  );
  assert.deepEqual(groupFollowupTasks([], "supplier"), []);
});
