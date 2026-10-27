import { StatCard, StatGrid } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { Workbench } from "../types/workbench";
import { todoLabels } from "../types/workbench";

/** 工作台关键指标：待办计数（不受待办筛选影响）与本月任务完成、有效已收票，全部来自后端。 */
export function WorkbenchKpis({ data }: { data: Workbench }) {
  const { counts, month } = data;
  // 只展示有金额的币种：没有已收票的分组（含币种待核实的任务）不占主数值；人民币优先
  const received = month.received
    .filter((item) => item.amount !== null && Number(item.amount) !== 0)
    .sort((a, b) => Number(b.currency === "CNY") - Number(a.currency === "CNY"));
  const [firstReceived, ...otherReceived] = received;
  const currency = (code: string) => (code === "CNY" ? "¥" : code || "币种待核实");
  return (
    <StatGrid label="关键指标" min={190}>
      <StatCard
        glyph="审"
        tone={counts.review > 0 ? "warning" : "neutral"}
        label={todoLabels.review}
        value={`${counts.review} 张`}
        note="报关单待财务审核或来源变化需重审"
      />
      <StatCard
        glyph="比"
        tone={counts.reverify > 0 ? "warning" : "neutral"}
        label={todoLabels.matching}
        value={`${counts.matching} 项`}
        note={counts.reverify > 0 ? `其中 ${counts.reverify} 条分配待复核` : "待审核的比对建议与待复核分配"}
      />
      <StatCard
        glyph="票"
        label={todoLabels.task}
        value={`${counts.task} 个`}
        note="未完成、未被替代的开票任务"
      />
      <StatCard
        glyph="月"
        tone="primary"
        label="本月任务完成"
        value={month.percent === null ? "—" : `${month.percent}%`}
        note={month.percent === null ? "本月暂无新建任务" : `已完成 ${month.completed} / ${month.total} 项`}
      />
      <StatCard
        glyph="收"
        label="本月有效已收票"
        value={
          firstReceived ? `${currency(firstReceived.currency)} ${money(firstReceived.amount)}` : "¥ 0.00"
        }
        note={
          otherReceived.length
            ? `另有 ${otherReceived.map((item) => `${currency(item.currency)} ${money(item.amount)}`).join("；")}`
            : firstReceived
              ? "本月新建任务中比对通过的发票金额"
              : "本月新建任务暂无比对通过的发票"
        }
      />
    </StatGrid>
  );
}
