import { useEffect, useRef, useState } from "react";
import { Alert, Button, ErrorState, Skeleton, Tabs } from "../../../shared/components/ui";
import { cancelBatch, getBatch, markDocumentsReady, recordRemittance, settleBatch } from "../api";
import type { BatchDetail } from "../types";
import { BatchCancelDialog } from "./BatchCancelDialog";
import { BatchDocuments } from "./BatchDocuments";
import { BatchOverview } from "./BatchOverview";
import { BatchRemittanceForm } from "./BatchRemittanceForm";
import "./hk-batch-detail.css";

type State = { kind: "loading" } | { kind: "ready"; batch: BatchDetail } | { kind: "error"; message: string };
export type BatchSection = "documents" | "remit";

/** 独立页与兼容详情入口共用资料、汇回和作废流程，切换页签不卸载资料组件。 */
export function BatchWorkspace({
  batchId,
  onChanged,
  onBusyChange,
  initialMode = "none",
  section,
  onSectionChange,
}: {
  batchId: number;
  onChanged?: () => void;
  onBusyChange?: (busy: boolean) => void;
  initialMode?: "none" | "remit";
  section?: BatchSection;
  onSectionChange?: (section: BatchSection) => void;
}) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [busy, setBusy] = useState(false);
  const [documentsBusy, setDocumentsBusy] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [documentsRevision, setDocumentsRevision] = useState(0);
  const [localSection, setLocalSection] = useState<BatchSection>(
    initialMode === "remit" ? "remit" : "documents",
  );
  const [cancelling, setCancelling] = useState(false);
  const submitting = useRef(false);
  const activeSection = section ?? localSection;
  const actionBusy = busy || documentsBusy;

  useEffect(() => {
    onBusyChange?.(actionBusy);
  }, [onBusyChange, actionBusy]);
  useEffect(() => {
    const controller = new AbortController();
    getBatch(batchId, controller.signal)
      .then((batch) => {
        if (!controller.signal.aborted) setState({ kind: "ready", batch });
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted)
          setState({ kind: "error", message: reason instanceof Error ? reason.message : "批次读取失败" });
      });
    return () => controller.abort();
  }, [batchId, refresh]);

  function selectSection(value: BatchSection) {
    setLocalSection(value);
    onSectionChange?.(value);
  }
  async function run(action: () => Promise<BatchDetail>) {
    if (submitting.current || documentsBusy) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      const batch = await action();
      setState({ kind: "ready", batch });
      setDocumentsRevision((value) => value + 1);
      setCancelling(false);
      onChanged?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "操作失败，填写内容已保留");
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  function documentsChanged() {
    // 只更新批次许可，不切换为加载状态，保留资料清单及用户所在页签。
    getBatch(batchId)
      .then((batch) => setState({ kind: "ready", batch }))
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "批次状态刷新失败"));
    onChanged?.();
  }
  if (state.kind === "loading") return <Skeleton rows={4} label="正在读取批次" />;
  if (state.kind === "error")
    return (
      <ErrorState
        title="批次读取失败"
        message={state.message}
        action={
          <Button
            onClick={() => {
              setState({ kind: "loading" });
              setRefresh((value) => value + 1);
            }}
          >
            重试
          </Button>
        }
      />
    );

  const batch = state.batch;
  return (
    <div className="settlement-page">
      <BatchOverview batch={batch} />
      <Tabs
        label="批次资料视图"
        items={[
          { key: "documents", label: "资料办理" },
          { key: "remit", label: "汇回登记" },
        ]}
        value={activeSection}
        onChange={selectSection}
      />
      {error && !cancelling && (
        <Alert tone="danger" title="操作未完成">
          {error}
        </Alert>
      )}
      <div hidden={activeSection !== "documents"}>
        {batch.route === "hk_transit" && batch.status !== "cancelled" ? (
          <BatchDocuments
            target={batch.id}
            standalone
            revision={documentsRevision}
            onChanged={documentsChanged}
            onBusyChange={setDocumentsBusy}
            actions={
              <>
                <Button
                  disabled={actionBusy || !batch.actions.settle.allowed}
                  title={batch.actions.settle.reason}
                  onClick={() => selectSection("remit")}
                >
                  登记汇回
                </Button>
                {batch.status === "collected" && (
                  <Button
                    variant="primary"
                    disabled={actionBusy || !batch.actions.documentsReady.allowed}
                    title={batch.actions.documentsReady.reason}
                    onClick={() => void run(() => markDocumentsReady(batch.id))}
                  >
                    确认资料已出
                  </Button>
                )}
                {!batch.actions.documentsReady.allowed && batch.status === "collected" && (
                  <p className="settlement-form__hint">{batch.actions.documentsReady.reason}</p>
                )}
                {batch.actions.cancel.allowed && (
                  <Button
                    variant="ghost"
                    disabled={actionBusy}
                    onClick={() => {
                      setError("");
                      setCancelling(true);
                    }}
                  >
                    作废批次
                  </Button>
                )}
              </>
            }
          />
        ) : (
          <Alert tone="info" title={batch.statusLabel}>
            {batch.cancelReason || batch.actions.documentsReady.reason}
            {batch.route === "direct" && (
              <Button
                disabled={actionBusy || !batch.actions.settle.allowed}
                onClick={() => void run(() => settleBatch(batch.id))}
              >
                确认已结汇
              </Button>
            )}
          </Alert>
        )}
      </div>
      <div hidden={activeSection !== "remit"}>
        <BatchRemittanceForm
          batch={batch}
          busy={actionBusy}
          onCancel={() => selectSection("documents")}
          onSubmit={(body) => void run(() => recordRemittance(batch.id, body))}
        />
      </div>
      {cancelling && (
        <BatchCancelDialog
          busy={actionBusy}
          error={error}
          onClose={() => setCancelling(false)}
          onSubmit={(reason) => void run(() => cancelBatch(batch.id, reason))}
        />
      )}
    </div>
  );
}
