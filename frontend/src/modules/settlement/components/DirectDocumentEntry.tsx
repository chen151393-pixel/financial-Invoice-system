import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { directDocumentGroupPath } from "../../../app/paths";
import { Button, ErrorState, Skeleton } from "../../../shared/components/ui";
import { ensureSingleDocumentGroup } from "../api/document-group-api";

/** 兼容旧单票资料链接；首次办理才创建真实单票组，不在列表加载时批量写入。 */
export function DirectDocumentEntry({ number }: { number: string }) {
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    ensureSingleDocumentGroup(number, abort.signal)
      .then((group) => {
        if (!abort.signal.aborted) navigate(directDocumentGroupPath(group.id), { replace: true });
      })
      .catch((e: unknown) => {
        if (!abort.signal.aborted) setError(e instanceof Error ? e.message : "资料组打开失败");
      });
    return () => abort.abort();
  }, [number, navigate, retry]);
  return error ? (
    <ErrorState
      title="资料组打开失败"
      message={error}
      action={
        <Button
          onClick={() => {
            setError("");
            setRetry((n) => n + 1);
          }}
        >
          重试
        </Button>
      }
    />
  ) : (
    <Skeleton rows={4} label="正在打开单票资料组" />
  );
}
