import { Alert } from "../../../shared/components/ui";
import type { CustomsImportJob } from "../customs-types";
import { ImportOutcome } from "./CustomsImportResult";

export function CustomsImportJobs({ jobs, error }: { jobs: CustomsImportJob[]; error: string }) {
  return (
    <div className="cm-import__jobs" aria-label="后台导入记录" aria-live="polite">
      {error && (
        <Alert tone="warning" title="暂时无法确认导入进度">
          {error}。请勿重复上传。
        </Alert>
      )}
      {jobs.map((job) => (
        <Alert
          key={job.id}
          tone={job.status === "failed" ? "danger" : job.status === "completed" ? "success" : "info"}
          title={`${job.fileName} · ${job.statusLabel}`}
        >
          {job.status === "completed" && job.result ? (
            <>
              已保存 {job.result.declarations.length} 张报关单、{job.result.rows} 项明细；新增{" "}
              {job.result.created} 张，更新 {job.result.replaced} 张，内容未变 {job.result.unchanged} 张。
              <details>
                <summary>查看逐张导入结果</summary>
                <ImportOutcome result={job.result} />
              </details>
            </>
          ) : job.status === "failed" ? (
            <>{job.error}。本文件未导入，列表中的原有数据未被此文件替换。请修正后重新上传。</>
          ) : (
            <>文件已接收，尚未导入完成。可关闭弹窗，后台继续处理，完成后列表自动刷新。</>
          )}
        </Alert>
      ))}
    </div>
  );
}
