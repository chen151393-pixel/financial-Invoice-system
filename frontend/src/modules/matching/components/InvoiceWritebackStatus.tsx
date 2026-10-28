import { useEffect, useState } from "react";
import { Link } from "react-router";
import { writebackRequestPath } from "../../../app/paths";
import { Alert, Button } from "../../../shared/components/ui";
import { invoiceReadiness, recheckInvoice } from "../../writeback/api";

export function InvoiceWritebackStatus({ invoiceId, version }: { invoiceId: string; version: object }) {
  const [result, setResult] = useState<Awaited<ReturnType<typeof invoiceReadiness>> | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    invoiceReadiness(invoiceId)
      .then((data) => {
        if (active) {
          setResult(data);
          setError("");
        }
      })
      .catch((e: unknown) => {
        if (active) setError(e instanceof Error ? e.message : "回写准备状态加载失败");
      });
    return () => {
      active = false;
    };
  }, [invoiceId, version]);
  async function recheck() {
    setBusy(true);
    try {
      setResult(await recheckInvoice(invoiceId));
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "重新检查失败");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Alert title="NS 回写准备" tone={error ? "danger" : "info"}>
      <p>{error || result?.reason || "正在读取准备状态…"}</p>
      {result?.task && (
        <p>
          <Link to={writebackRequestPath(result.task.id)}>查看回写任务 · {result.task.stateLabel}</Link>
        </p>
      )}
      <Button disabled={busy} onClick={() => void recheck()}>
        {busy ? "正在检查" : "重新检查整票"}
      </Button>
    </Alert>
  );
}
