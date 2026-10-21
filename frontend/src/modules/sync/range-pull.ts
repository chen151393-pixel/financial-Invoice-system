import type { DateRange, PullCursor, PullResult } from "./api";

type RangePullOptions = {
  range: DateRange;
  save: boolean;
  readPage: (offset: number, range: DateRange, save: boolean, cursor?: PullCursor) => Promise<PullResult>;
  onPage: (page: PullResult) => void;
  shouldStop: () => boolean;
};

/** 按服务端游标串行加载；停止只影响下一批，不中断结果可能未知的保存请求。 */
export async function pullDateRange(options: RangePullOptions): Promise<"completed" | "partial" | "stopped"> {
  const range = { ...options.range };
  let offset = 0;
  let cursor: PullCursor = { afterId: "0", throughId: null, offset: 0 };
  let partial = false;
  while (!options.shouldStop()) {
    const page = await options.readPage(offset, range, options.save, cursor);
    options.onPage(page);
    if (page.batch?.canContinue === false) throw new Error(page.message);
    if (page.batch?.status === "partial") partial = true;
    if (!page.hasMore) return partial ? "partial" : "completed";
    if (page.nextOffset === null || !Number.isInteger(page.nextOffset) || page.nextOffset <= offset) {
      throw new Error("分页位置异常，已停止后续拉取，请核实已完成批次后重新查询");
    }
    const next = page.nextCursor;
    if (
      !next ||
      (next.afterId === cursor.afterId &&
        next.throughId === cursor.throughId &&
        next.offset === cursor.offset)
    ) {
      throw new Error("范围游标异常，已停止后续拉取，请核实已完成批次后刷新页面");
    }
    offset = page.nextOffset;
    cursor = next;
  }
  return "stopped";
}
