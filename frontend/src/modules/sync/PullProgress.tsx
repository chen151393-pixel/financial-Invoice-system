import type { SyncProgress } from "./api";

export function PullProgress({
  progress,
  unavailable,
}: {
  progress: SyncProgress | null;
  unavailable: boolean;
}) {
  if (unavailable)
    return (
      <p role="status" className="sync-page__scope-change">
        进度暂时无法更新，正在等待本批保存响应。请勿重复提交。
      </p>
    );
  if (!progress) return null;
  return (
    <p role="status" className="sync-page__result-summary">
      当前阶段：{progress.label}
      {progress.total !== null &&
        progress.completed !== null &&
        `（${progress.completed} / ${progress.total}）`}
      {` · 本批已用时 ${progress.elapsedSeconds} 秒`}
      {progress.state === "completed" && " · 等待保存响应确认"}
    </p>
  );
}
