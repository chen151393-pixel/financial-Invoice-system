// 演示数据的内存状态：按数据集初始化记录，列表状态随预览、确认、核实变化。
import { HttpError } from "../../../shared/api/http";
import type { WritebackItem, WritebackRequest } from "../types";
import { executed, preview, type DemoDataset } from "./demo-builders";
import type { DemoSet } from "./demo-mode";
import { dataset as first } from "./demo-set-1";
import { dataset as second } from "./demo-set-2";

export const datasets: Record<DemoSet, DemoDataset> = { "1": first, "2": second };
interface State {
  requests: Map<string, WritebackRequest>;
  latest: Map<string, string>;
  polls: Map<string, number>;
}
const states = new Map<DemoSet, State>();
const notes: Record<string, string> = {
  pending: "预览已生成，待确认",
  executing: "正在等待 NS 返回",
  unknown: "NS 响应超时，相关账单已锁定",
  failed: "NS 未写入，可重新生成预览",
  succeeded: "NS 发票记录 #48213",
};

export function state(set: DemoSet): State {
  const existing = states.get(set);
  if (existing) return existing;
  const data = datasets[set];
  const created: State = { requests: new Map(), latest: new Map(), polls: new Map() };
  for (const record of data.records) {
    const item = data.items.find((row) => row.invoiceId === record.invoiceId)!;
    const spec = data.specs[record.invoiceId];
    const pending = preview(item, record.requestId, spec);
    const value =
      record.state === "pending"
        ? pending
        : record.state === "executing"
          ? {
              ...executed(pending, "unknown"),
              phase: "executing" as const,
              label: "执行中",
              message: "已提交 NS，正在等待返回",
              poll: true,
              verify: { allowed: false, reason: "执行中，请稍候" },
            }
          : executed(pending, record.state, spec.changedReceived);
    created.requests.set(record.requestId, value);
    created.latest.set(record.invoiceId, record.requestId);
  }
  states.set(set, created);
  return created;
}

export function current(set: DemoSet, item: WritebackItem): WritebackItem {
  const id = state(set).latest.get(item.invoiceId);
  const request = id ? state(set).requests.get(id) : undefined;
  if (!request || request.phase === item.phase) return item;
  return { ...item, phase: request.phase, label: request.label, requestId: id!, note: notes[request.phase] };
}

/** 执行中或待核实的记录转为成功：沿用原执行记录，只追加本次结果，不重复确认与提交。 */
export function finished(request: WritebackRequest, action: string, detail: string): WritebackRequest {
  const done = executed({ ...request, phase: "pending" }, "succeeded");
  return {
    ...done,
    events: [...request.events, { at: new Date().toISOString(), action, actor: "系统", detail }],
  };
}

export function find(set: DemoSet, requestId: string) {
  const request = state(set).requests.get(requestId);
  if (!request) throw new HttpError("未找到这条回写记录", 404);
  return request;
}
