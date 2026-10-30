import { Button } from "../Button";
import { Badge } from "./Badge";
import { DataTable } from "./DataTable";
import type { BatchUploadRow } from "./BatchUpload";

/** 逐文件真实结果；编号纠正和重传只发回调用方，组件不判断归档资格。 */
export function BatchUploadResults({
  rows,
  busy,
  targetLabel,
  targetMaxLength,
  statusLabels,
  assignable,
  onAssign,
  onRetry,
}: {
  rows: BatchUploadRow[];
  busy: boolean;
  targetLabel: string;
  targetMaxLength: number;
  statusLabels: Record<string, string>;
  assignable: readonly string[];
  onAssign: (index: number, target: string) => void;
  onRetry: (row: BatchUploadRow) => void;
}) {
  return (
    <DataTable
      label="本次逐文件处理结果"
      minWidth={0}
      density="compact"
      rows={rows}
      rowKey={(row) => String(row.index)}
      columns={[
        {
          key: "file",
          header: `文件 / ${targetLabel}`,
          width: "46%",
          render: (row) => (
            <>
              <strong className="ui-upload__filename">{row.result.filename}</strong>
              <span className="ui-upload__target">{row.result.target || `${targetLabel}待识别`}</span>
            </>
          ),
        },
        {
          key: "result",
          header: "处理结果",
          render: (row) => (
            <>
              <Badge
                tone={
                  row.result.status === "saved"
                    ? "success"
                    : row.result.status === "failed"
                      ? "danger"
                      : "warning"
                }
              >
                {statusLabels[row.result.status] ?? row.result.status}
              </Badge>
              <p className="ui-upload__reason">{row.result.reason}</p>
              {row.result.paths.length > 0 && (
                <details className="ui-upload__paths">
                  <summary>查看保存位置</summary>
                  {row.result.paths.map((path) => (
                    <span key={path} className="ui-upload__path">
                      {path}
                    </span>
                  ))}
                </details>
              )}
              {assignable.includes(row.result.status) && (
                <div className="ui-upload__assign">
                  <input
                    aria-label={`指定${targetLabel}：${row.result.filename}`}
                    placeholder={`填写${targetLabel}`}
                    value={row.target}
                    maxLength={targetMaxLength}
                    disabled={busy}
                    onChange={(event) => onAssign(row.index, event.target.value)}
                  />
                  <Button size="sm" disabled={busy || !row.target.trim()} onClick={() => onRetry(row)}>
                    按此编号重新上传
                  </Button>
                </div>
              )}
            </>
          ),
        },
      ]}
    />
  );
}
