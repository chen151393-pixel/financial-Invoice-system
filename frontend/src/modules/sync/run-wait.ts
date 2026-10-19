import { HttpError } from "../../shared/api/http";
import type { NsRun, PullResult } from "./api";

type WaitOptions = {
  submit: () => Promise<NsRun>;
  read: () => Promise<NsRun>;
  onRun: (run: NsRun) => void;
  onUnavailable: () => void;
  isCurrent: () => boolean;
  delay?: number;
  wait?: (milliseconds: number) => Promise<void>;
};

// 提交结果不明且连续多次查不到记录时，才判定本批没有到达服务器。
const MISSING_CHECKS = 3;
const LEFT = "已离开本批查询；本批可能仍在后台执行，返回本页会按请求编号恢复查看";

function sleep(milliseconds: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, milliseconds));
}

/** 已结束批次转为单批结果；失败与待核实直接给出后端原因，不推断是否已保存。 */
export function settleRun(run: NsRun): PullResult {
  const saved = run.status === "completed" || run.status === "partial" || run.status === "interrupted";
  if (saved && run.result) return run.result;
  throw new Error(run.error ? `${run.statusLabel}（${run.error}）` : run.statusLabel);
}

/**
 * 提交一次后只按原请求编号串行查询。网络中断、代理超时都不重新提交，也不当作失败；
 * 查询失败只提示进度暂不可用并继续查询，直到后端给出结束状态。
 */
export async function waitForRun(options: WaitOptions): Promise<PullResult> {
  const wait = options.wait ?? sleep;
  const delay = options.delay ?? 1000;
  let run: NsRun | null = null;
  let submitUnknown = false;
  try {
    run = await options.submit();
  } catch (error) {
    // 后端明确拒绝（参数、配置、冲突）时本批没有创建，直接展示原因。
    if (error instanceof HttpError && error.status < 500) throw error;
    submitUnknown = true;
    options.onUnavailable();
  }
  let missing = 0;
  while (!run || run.status === "running") {
    if (run) options.onRun(run);
    if (!options.isCurrent()) throw new Error(LEFT);
    await wait(delay);
    if (!options.isCurrent()) throw new Error(LEFT);
    try {
      run = await options.read();
    } catch (error) {
      if (error instanceof HttpError && error.status === 404 && submitUnknown) {
        missing += 1;
        if (missing >= MISSING_CHECKS) throw new Error("本批提交未到达服务器，未开始执行，可重新拉取");
      }
      options.onUnavailable();
    }
  }
  options.onRun(run);
  return settleRun(run);
}
