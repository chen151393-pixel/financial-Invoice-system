// 演示数据源：按计划中的 /api/writeback/* 契约在浏览器内存中应答，不发请求、不写 NS。
// 状态变化（生成预览、确认、核实）保留到刷新页面为止。
import { HttpError } from "../../../shared/api/http";
import type { WritebackList, WritebackQuery } from "../types";
import { executed, preview } from "./demo-builders";
import type { DemoSet } from "./demo-mode";
import { current, datasets, find, finished, state } from "./demo-store";

const wait = () => new Promise((resolve) => setTimeout(resolve, 400));

export async function demoList(set: DemoSet, query: WritebackQuery): Promise<WritebackList> {
  await wait();
  const data = datasets[set];
  const all = data.items.map((item) => current(set, item));
  const rows = all.filter(
    (item) =>
      (!query.phase || item.phase === query.phase) &&
      (!query.vendor || item.vendorName.includes(query.vendor)) &&
      (!query.invoiceNo || item.invoiceNo.includes(query.invoiceNo)) &&
      (!query.dateFrom || item.invoiceDate >= query.dateFrom) &&
      (!query.dateTo || item.invoiceDate <= query.dateTo),
  );
  const counts: WritebackList["counts"] = { all: all.length };
  for (const item of all) counts[item.phase] = (counts[item.phase] ?? 0) + 1;
  const start = (query.page - 1) * query.pageSize;
  return {
    items: rows.slice(start, start + query.pageSize),
    total: rows.length,
    page: query.page,
    pageSize: query.pageSize,
    pages: Math.max(1, Math.ceil(rows.length / query.pageSize)),
    counts,
    write: data.write,
  };
}

export async function demoCreatePreview(set: DemoSet, invoiceId: string, requestId: string) {
  await wait();
  const data = datasets[set];
  const item = data.items.find((row) => row.invoiceId === invoiceId);
  const spec = data.specs[invoiceId];
  if (!item || !item.preview.allowed || !spec)
    throw new HttpError(item?.preview.reason || "该发票不能生成预览", 409);
  const id = `WB-${requestId.slice(0, 8).toUpperCase()}`;
  const store = state(set);
  if (!store.requests.has(id)) store.requests.set(id, preview(item, id, spec));
  store.latest.set(invoiceId, id);
  return store.requests.get(id)!;
}

export async function demoGet(set: DemoSet, requestId: string) {
  await wait();
  const request = find(set, requestId);
  if (request.phase !== "executing") return request;
  // 执行中的记录轮询两次后返回成功结果。
  const store = state(set);
  const polls = (store.polls.get(requestId) ?? 0) + 1;
  store.polls.set(requestId, polls);
  if (polls < 2) return request;
  const done = finished(request, "NS 返回成功", "主记录 #48213");
  store.requests.set(requestId, done);
  return done;
}

export async function demoExecute(set: DemoSet, requestId: string) {
  await wait();
  const data = datasets[set];
  const request = find(set, requestId);
  if (request.phase !== "pending" || !request.execute.allowed)
    throw new HttpError(request.execute.reason, 409);
  if (!data.write.enabled) throw new HttpError("NS 写入未启用", 403);
  const spec = data.specs[request.invoiceId];
  const done = executed(request, data.outcome, spec?.changedReceived);
  state(set).requests.set(requestId, done);
  return done;
}

export async function demoVerify(set: DemoSet, requestId: string) {
  await wait();
  const request = find(set, requestId);
  if (request.phase !== "unknown") throw new HttpError(request.verify.reason, 409);
  // 演示：核实查到 NS 已完整写入。
  const done = finished(request, "核实：NS 已完整写入", "已释放账单锁");
  state(set).requests.set(requestId, done);
  return done;
}
