import { StageTabs, type Tone } from "../../../shared/components/ui";
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

/** 节点分区：一条流程带，左侧为进行中合计，各节点按流程排列（后端汇总全部筛选结果），点击按节点筛选。 */
export function BoardNodeTabs({
  nodes,
  openTotal,
  value,
  onChange,
}: {
  nodes: BoardNode[];
  openTotal: number;
  value: TaskBoardQuery["node"];
  onChange: (node: TaskBoardQuery["node"]) => void;
}) {
  return (
    <StageTabs
      label="按当前节点筛选任务"
      value={value}
      onChange={onChange}
      total={{ label: "进行中任务", count: openTotal, hint: "未完成、未被替代" }}
      items={nodes.map((node) => ({
        key: node.key,
        label: node.label,
        count: node.count,
        hint: node.hint,
        terminal: node.key === "done",
      }))}
    />
  );
}
