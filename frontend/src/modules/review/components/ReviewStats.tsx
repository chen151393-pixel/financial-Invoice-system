import { StatCard, StatGrid } from "../../../shared/components/ui";
import type { ComparisonResult } from "../types";

/** 财务核对概况：张数全部来自后端列表计数（随查询条件变化），前端只展示。 */
export function ReviewStats({ counts }: { counts: ComparisonResult["counts"] }) {
  return (
    <StatGrid label="核对概况">
      <StatCard glyph="全" label="全部报关单" value={`${counts.all} 张`} note="当前查询条件下" />
      <StatCard
        glyph="审"
        tone={counts.pending > 0 ? "warning" : "neutral"}
        label="待审核报关单"
        value={`${counts.pending} 张`}
        note={counts.changed > 0 ? `其中 ${counts.changed} 张来源变化需重审` : "审核通过后生成开票任务"}
      />
      <StatCard glyph="通" label="审核通过" value={`${counts.approved} 张`} note="可查看审核记录" />
      <StatCard
        glyph="月"
        label="本月审核通过"
        value={`${counts.approvedThisMonth} 张`}
        note="按北京时间自然月统计"
      />
    </StatGrid>
  );
}
