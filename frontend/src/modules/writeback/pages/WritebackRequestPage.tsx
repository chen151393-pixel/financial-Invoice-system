import { useState } from "react";
import { useNavigate } from "react-router";
import { writebackRequestPath } from "../../../app/paths";
import { Button } from "../../../shared/components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DemoBanner } from "../components/DemoBanner";
import { EventLog } from "../components/EventLog";
import { NotConnected } from "../components/NotConnected";
import { PreviewChecks } from "../components/PreviewChecks";
import { PreviewLines } from "../components/PreviewLines";
import { PreviewSummary } from "../components/PreviewSummary";
import { RequestHeader } from "../components/RequestHeader";
import { ResultRecords } from "../components/ResultRecords";
import { useCreatePreview } from "../hooks/useCreatePreview";
import { useWritebackRequest } from "../hooks/useWritebackRequest";
import "../writeback.css";
import "../writeback-request.css";

/** 一条回写记录：待确认时展示预览与确认入口，执行后展示后端记录的结果与核实信息。 */
export function WritebackRequestPage({ requestId }: { requestId: string }) {
  const { data, error, notConnected, action, refresh, execute, verify } = useWritebackRequest(requestId);
  const [confirming, setConfirming] = useState(false);
  const navigate = useNavigate();
  const repreview = useCreatePreview((next) => navigate(writebackRequestPath(next)));
  if (notConnected) return <NotConnected scope="无法读取这条回写记录。" />;
  if (!data)
    return (
      <section className="wb-panel wb-state" aria-label="回写记录">
        {error ? (
          <>
            <p role="alert" className="wb-error">
              {error}
            </p>
            <Button onClick={refresh}>重新读取</Button>
          </>
        ) : (
          <p role="status">正在读取回写记录…</p>
        )}
      </section>
    );
  const createError = repreview.error?.invoiceId === data.invoiceId ? repreview.error.message : "";
  return (
    <div className="wb-stack">
      <DemoBanner />
      <RequestHeader
        data={data}
        action={action}
        creating={repreview.busyInvoice === data.invoiceId}
        onConfirm={() => setConfirming(true)}
        onVerify={() => void verify()}
        onRefresh={refresh}
        onRepreview={() => void repreview.create(data.invoiceId)}
      />
      {(error || createError) && (
        <p role="alert" className="wb-panel wb-error">
          {error || createError}
        </p>
      )}
      <PreviewSummary data={data} />
      {data.phase === "pending" ? (
        <>
          <PreviewChecks checks={data.checks} />
          <PreviewLines data={data} />
        </>
      ) : (
        <ResultRecords data={data} />
      )}
      <EventLog events={data.events} />
      {confirming && (
        <ConfirmDialog
          data={data}
          busy={action === "execute"}
          onCancel={() => setConfirming(false)}
          onConfirm={() => {
            // 无论成功与否都关闭弹窗：结果以页面上后端返回的状态为准，避免在弹窗内重复提交。
            void execute().finally(() => setConfirming(false));
          }}
        />
      )}
    </div>
  );
}
