import type { NsRun } from "./api";

export function PullProgress({ run, unavailable }: { run: NsRun | null; unavailable: boolean }) {
  const reference = run ? `请求编号 ${run.requestId}` : "";
  if (unavailable)
    return (
      <p role="status" className="sync-page__scope-change">
        进度暂时无法更新，本批仍可能在后台执行，正在按请求编号继续查询结果。请勿重复提交。
        {reference && ` ${reference}`}
      </p>
    );
  if (!run) return null;
  const progress = run.progress;
  return (
    <p role="status" className="sync-page__result-summary">
      {progress ? (
        <>
          当前阶段：{progress.label}
          {progress.total !== null &&
            progress.completed !== null &&
            `（${progress.completed} / ${progress.total}）`}
          {` · 本批已用时 ${progress.elapsedSeconds} 秒`}
        </>
      ) : (
        "本批已提交，等待后台开始执行"
      )}
      {` · ${reference}`}
    </p>
  );
}
