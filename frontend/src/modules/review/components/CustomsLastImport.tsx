import { Button } from "../../../shared/components/ui";
import type { CustomsLastImportState } from "../useCustomsLastImport";

/** 上传区下方只显示一条上次成功入库的结果，不增加列表或分页。 */
export function CustomsLastImport({
  state,
  disabled,
  onRetry,
}: {
  state: CustomsLastImportState;
  disabled: boolean;
  onRetry: () => void;
}) {
  const source = state.kind === "ready" ? state.source : null;
  return (
    <div className="cm-import__last cm-muted" aria-label="上次导入结果" role="status">
      <span>上次导入：</span>
      {state.kind === "loading" && <span>正在读取…</span>}
      {state.kind === "error" && (
        <>
          <span>{state.message}</span>
          <Button variant="ghost" size="sm" disabled={disabled} onClick={onRetry}>
            重新读取
          </Button>
        </>
      )}
      {state.kind === "ready" &&
        (!source ? (
          <span>暂无记录</span>
        ) : (
          <>
            <strong className="cm-import__last-file" title={source.fileName}>
              {source.fileName}
            </strong>
            <span>已导入 {source.receiptCount} 张回执</span>
            <span>{source.importedByName || source.importedBy}</span>
            <time dateTime={source.importedAt} title="北京时间">
              {new Date(source.importedAt).toLocaleString("zh-CN", {
                timeZone: "Asia/Shanghai",
                hour12: false,
              })}
            </time>
          </>
        ))}
    </div>
  );
}
