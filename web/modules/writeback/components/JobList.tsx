import { Button } from "../../../shared/components/Button";
import { Panel } from "../../../shared/components/Panel";
import type { Job } from "../api";

export function JobList({
  jobs,
  busy,
  onRefresh,
  onSelect,
}: {
  jobs: Job[];
  busy: boolean;
  onRefresh: () => void;
  onSelect: (id: string) => void;
}) {
  return (
    <Panel
      title="最近 25 个预览与写入任务"
      actions={
        <Button disabled={busy} onClick={onRefresh}>
          刷新
        </Button>
      }
    >
      {jobs.length === 0 ? (
        <p>暂无记录</p>
      ) : (
        jobs.map((job) => (
          <div className="live-heading" key={job.id}>
            <p>
              {job.target} · {job.state}
            </p>
            <Button disabled={busy} onClick={() => onSelect(job.id)}>
              查看任务
            </Button>
          </div>
        ))
      )}
    </Panel>
  );
}
