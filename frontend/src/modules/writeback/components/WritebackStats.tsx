import { StatCard, StatGrid } from "../../../shared/components/ui";
import type { TaskList, WritebackGroup } from "../types";

export const groupLabels = {
  all: "全部任务",
  pending: "待回写",
  executing: "回写中",
  applied: "NS 已登记",
  attention: "需处理",
  stale: "审核已失效",
} as const;

export function WritebackStats({
  counts,
  selected,
  onSelect,
}: {
  counts: TaskList["counts"];
  selected: string;
  onSelect: (group: WritebackGroup) => void;
}) {
  return (
    <StatGrid label="回写概况">
      <StatCard
        glyph="待"
        label="待回写"
        value={`${counts.pending} 张`}
        note="待匹配、等待账单、待确认及待写入 NS"
        selected={selected === "pending"}
        onSelect={() => onSelect("pending")}
      />
      <StatCard
        glyph="写"
        tone="primary"
        label="回写中"
        value={`${counts.executing} 张`}
        note="已提交 NS，等待处理结果，请勿重复提交"
        selected={selected === "executing"}
        onSelect={() => onSelect("executing")}
      />
      <StatCard
        glyph="成"
        label="NS 已登记"
        value={`${counts.applied} 张`}
        note="包含本次回写、同号已有登记及人工核实"
        selected={selected === "applied"}
        onSelect={() => onSelect("applied")}
      />
      <StatCard
        glyph="核"
        tone={counts.attention ? "warning" : "neutral"}
        label="需处理"
        value={`${counts.attention} 张`}
        note="待处理、部分写入或结果不明"
        selected={selected === "attention"}
        onSelect={() => onSelect("attention")}
      />
    </StatGrid>
  );
}
