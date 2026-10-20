import type { Allocation } from "../types/matching";

/**
 * 按后端返回的状态把分配分成三组展示，不改变也不推断业务状态：
 * 已关联＝已通过且依据有效；待处理＝待审核建议或需重新核实；历史＝已驳回或已取消。
 */
export function groupAllocations(allocations: Allocation[]) {
  const linked: Allocation[] = [];
  const pending: Allocation[] = [];
  const history: Allocation[] = [];
  for (const allocation of allocations) {
    if (allocation.status === "proposed") pending.push(allocation);
    else if (allocation.status === "confirmed")
      (allocation.verificationStatus === "valid" ? linked : pending).push(allocation);
    else history.push(allocation);
  }
  return { linked, pending, history };
}
