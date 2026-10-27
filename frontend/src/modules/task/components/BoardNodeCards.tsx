import { StatCard, StatGrid, type StatTone, type Tone } from "../../../shared/components/ui";
import type { BoardNode, BoardNodeKey, TaskBoardQuery } from "../types/board";

// 节点在界面上的语义：橙=待采购处理，蓝=等供应商，紫=部分收票，绿=已完成（与开票跟进状态色一致）
export const NODE_TONES: Record<BoardNodeKey, Tone> = {
  documents: "warning",
  notification: "warning",
  invoices: "info",
  comparison: "progress",
  completion: "warning",
  done: "success",
};

// 节点卡片的字标；文字为一个字，图块只作识别，状态另有标签文字
export const NODE_GLYPHS: Record<BoardNodeKey, string> = {
  documents: "合",
  notification: "通",
  invoices: "票",
  comparison: "部",
  completion: "补",
  done: "完",
};

// 合同与资料靠采购补齐，有积压时用橙色提醒
const NODE_STAT_TONES: Partial<Record<BoardNodeKey, StatTone>> = {
  documents: "warning",
  completion: "warning",
};

/** 节点卡片：进行中合计 + 六个节点一行排开（后端汇总全部筛选结果），点击按节点筛选。 */
export function BoardNodeCards({
  nodes,
  openTotal,
  value,
  onChange,
  showOpenTotal = true,
}: {
  nodes: BoardNode[];
  openTotal: number;
  value: TaskBoardQuery["node"];
  onChange: (node: TaskBoardQuery["node"]) => void;
  showOpenTotal?: boolean;
}) {
  return (
    <StatGrid label="按当前节点筛选任务" min={130}>
      {showOpenTotal && (
        <StatCard
          compact
          glyph="进"
          tone="primary"
          label="进行中任务"
          value={`${openTotal} 个`}
          note="未完成、未被替代"
          selected={value === ""}
          onSelect={() => onChange("")}
        />
      )}
      {nodes.map((node) => (
        <StatCard
          key={node.key}
          compact
          glyph={NODE_GLYPHS[node.key]}
          tone={node.count > 0 ? (NODE_STAT_TONES[node.key] ?? "neutral") : "neutral"}
          label={node.label}
          value={`${node.count} 个`}
          note={node.hint}
          selected={value === node.key}
          onSelect={() => onChange(node.key)}
        />
      ))}
    </StatGrid>
  );
}
