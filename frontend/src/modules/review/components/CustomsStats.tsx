import { StatCard, StatGrid } from "../../../shared/components/ui";
import type { CustomsCounts, CustomsFilter } from "../customs-types";

/** 海关回执比对概况：张数全部来自后端计数（随查询条件变化）；点击切换下方列表筛选。 */
export function CustomsStats({
  counts,
  value,
  onSelect,
}: {
  counts: CustomsCounts;
  value: CustomsFilter;
  onSelect: (status: CustomsFilter) => void;
}) {
  return (
    <StatGrid label="比对概况">
      <StatCard
        glyph="回"
        tone="primary"
        label="海关回执"
        value={`${counts.receipts} 张`}
        note={`共 ${counts.items} 项明细`}
        selected={value === "all"}
        onSelect={() => onSelect("all")}
      />
      <StatCard
        glyph="符"
        label="明细一致"
        value={`${counts.matched} 张`}
        note={
          counts.splitMatched > 0 ? `其中拆行或合并一致 ${counts.splitMatched} 张` : "品名、单位、数量均一致"
        }
        selected={value === "matched"}
        onSelect={() => onSelect("matched")}
      />
      <StatCard
        glyph="差"
        tone={counts.different > 0 ? "warning" : "neutral"}
        label="数量或单位不一致"
        value={`${counts.different} 张`}
        note="在 NS 修正后重新匹配"
        selected={value === "different"}
        onSelect={() => onSelect("different")}
      />
      <StatCard
        glyph="缺"
        tone={counts.nsMissing > 0 ? "warning" : "neutral"}
        label="未找到 NS 报关单"
        value={`${counts.nsMissing} 张`}
        note="按真实报关单号未能唯一对应"
        selected={value === "ns_missing"}
        onSelect={() => onSelect("ns_missing")}
      />
    </StatGrid>
  );
}
