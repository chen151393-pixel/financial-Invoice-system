import { useEffect, useRef, useState } from "react";
import { Alert, Button, DataTable, Dialog, ErrorState, Skeleton } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import { confirmGroupBasis, previewGroupBasis } from "../api/document-group-api";
import type { DocumentGroup, GroupBasisPreview } from "../types/document-group";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; value: GroupBasisPreview };
/** 来源更正须先展示前后依据，经办人确认后才恢复办理。 */
export function DocumentGroupBasisDialog({
  id,
  onClose,
  onSaved,
}: {
  id: number;
  onClose: () => void;
  onSaved: (group: DocumentGroup) => void;
}) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [retry, setRetry] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submitting = useRef(false);
  useEffect(() => {
    const abort = new AbortController();
    previewGroupBasis(id, abort.signal)
      .then((value) => {
        if (!abort.signal.aborted) setState({ kind: "ready", value });
      })
      .catch((reason: unknown) => {
        if (!abort.signal.aborted)
          setState({ kind: "error", message: reason instanceof Error ? reason.message : "来源读取失败" });
      });
    return () => abort.abort();
  }, [id, retry]);
  async function confirm() {
    if (submitting.current || state.kind !== "ready" || !state.value.update.allowed) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      onSaved(await confirmGroupBasis(id, state.value.token));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "来源更新失败");
      setState({ kind: "loading" });
      setRetry((n) => n + 1);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return (
    <Dialog title="核对并更新资料组来源" onClose={onClose} busy={busy}>
      <div className="settlement-detail">
        {state.kind === "loading" && <Skeleton rows={3} label="正在核对当前来源" />}
        {state.kind === "error" && (
          <ErrorState
            title="来源读取失败"
            message={state.message}
            action={
              <Button
                onClick={() => {
                  setState({ kind: "loading" });
                  setRetry((n) => n + 1);
                }}
              >
                重试
              </Button>
            }
          />
        )}
        {state.kind === "ready" && (
          <>
            <DataTable
              label="来源更新前后对照"
              rows={[
                { label: "境外收货人", before: state.value.oldConsignee, after: state.value.newConsignee },
                { label: "币种", before: state.value.oldCurrency, after: state.value.newCurrency },
              ]}
              rowKey={(row) => row.label}
              columns={[
                { key: "field", header: "字段", render: (row) => row.label },
                { key: "before", header: "原组依据", render: (row) => row.before },
                { key: "after", header: "当前报关依据", render: (row) => row.after },
              ]}
              minWidth={360}
            />
            <p>
              当前 {state.value.declarationCount} 张报关单 · {state.value.newCurrency}{" "}
              {state.value.amount ? money(state.value.amount) : "—"}
            </p>
            <Alert tone="info" title="确认后按当前来源继续办理">
              保留现有提单和合同；合同按当前依据重新核对，失效的合同需重新生成。此次操作会记录更新前后依据和经办人。
            </Alert>
            {!state.value.update.allowed && (
              <Alert tone="warning" title="暂不能更新">
                {state.value.update.reason}
              </Alert>
            )}
            <div className="settlement-form__actions">
              <Button disabled={busy} onClick={onClose}>
                取消
              </Button>
              <Button
                variant="primary"
                disabled={busy || !state.value.update.allowed}
                onClick={() => void confirm()}
              >
                {busy ? "正在更新…" : "确认更新来源"}
              </Button>
            </div>
          </>
        )}
        {error && (
          <Alert tone="danger" title="请核对更新结果">
            {error}
          </Alert>
        )}
      </div>
    </Dialog>
  );
}
