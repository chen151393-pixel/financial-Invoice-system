import { Button } from "../../../shared/components/Button";
import { writebackTime, type WritebackRequest } from "../types";
import { WritebackPhaseTag } from "./WritebackPhaseTag";

/**
 * 回写记录的状态与操作。每个按钮的可用性和原因都来自后端；
 * 结果待核实时只提供“核实”，不提供重新提交。
 */
export function RequestHeader({
  data,
  action,
  creating,
  onConfirm,
  onVerify,
  onRefresh,
  onRepreview,
}: {
  data: WritebackRequest;
  action: "" | "execute" | "verify";
  creating: boolean;
  onConfirm: () => void;
  onVerify: () => void;
  onRefresh: () => void;
  onRepreview: () => void;
}) {
  const busy = action !== "" || creating;
  const repreview = (data.phase === "pending" || data.phase === "failed") && (
    <Button
      variant={data.phase === "failed" ? "primary" : "secondary"}
      disabled={busy || !data.refresh.allowed}
      onClick={onRepreview}
    >
      {creating ? "正在生成…" : "重新生成预览"}
    </Button>
  );
  const reasons = [
    data.phase === "pending" && !data.execute.allowed && data.execute.reason,
    data.phase === "unknown" && !data.verify.allowed && data.verify.reason,
    (data.phase === "pending" || data.phase === "failed") && !data.refresh.allowed && data.refresh.reason,
  ].filter(Boolean);
  return (
    <section className={`wb-panel wb-request-head wb-request-head--${data.phase}`} aria-label="回写状态">
      <div className="wb-request-head__main">
        <div className="wb-inline">
          <WritebackPhaseTag phase={data.phase} label={data.label} />
          <strong>{data.message}</strong>
        </div>
        {data.phase === "pending" && (
          <span className="wb-muted">预览有效至 {writebackTime(data.expiresAt)}</span>
        )}
        {reasons.map((reason) => (
          <span key={String(reason)} className="wb-note wb-note--blocked">
            {reason}
          </span>
        ))}
      </div>
      <div className="wb-inline">
        {data.phase === "executing" && <Button onClick={onRefresh}>刷新状态</Button>}
        {repreview}
        {data.phase === "pending" && (
          <Button variant="primary" disabled={busy || !data.execute.allowed} onClick={onConfirm}>
            确认回写 NS
          </Button>
        )}
        {data.phase === "unknown" && (
          <Button variant="primary" disabled={busy || !data.verify.allowed} onClick={onVerify}>
            {action === "verify" ? "正在核实…" : "核实 NS 结果"}
          </Button>
        )}
      </div>
    </section>
  );
}
