import type { TaskSummary } from "../types";

export function ParentOrderNumbers({ task }: { task: TaskSummary }) {
  return task.parentOrders?.length ? (
    <div className="wb-parent-orders">
      {task.parentOrders.map((parent) => (
        <span key={`${parent.id}:${parent.number}`}>{parent.number || `NS ID：${parent.id}`}</span>
      ))}
    </div>
  ) : (
    <span className="wb-secondary">未记录</span>
  );
}
