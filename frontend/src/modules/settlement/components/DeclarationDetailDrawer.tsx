import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { Button, Dialog, ErrorState, Skeleton } from "../../../shared/components/ui";
import { getDeclarationDetail } from "../api/declaration-detail-api";
import type { DeclarationDetail } from "../types/declaration-detail";
import { DeclarationDetailBody } from "./DeclarationDetailBody";
import "./declaration-detail.css";

type State =
  | { kind: "loading" }
  | { kind: "ready"; detail: DeclarationDetail }
  | { kind: "error"; message: string };

export function DeclarationDetailDrawer({ number, onClose }: { number: string; onClose: () => void }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    getDeclarationDetail(number, controller.signal)
      .then((detail) => {
        if (!controller.signal.aborted) setState({ kind: "ready", detail });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setState({ kind: "error", message: error instanceof Error ? error.message : "加载失败，请重试" });
      });
    return () => controller.abort();
  }, [number, revision]);
  return (
    <Dialog
      title="报关单结汇详情"
      placement="right"
      onClose={onClose}
      className="settlement-declaration-drawer"
    >
      {state.kind === "loading" && <Skeleton rows={8} label="正在读取报关单结汇详情" />}
      {state.kind === "error" && (
        <ErrorState
          title="报关单结汇详情读取失败"
          message={state.message}
          action={
            <Button
              onClick={() => {
                setState({ kind: "loading" });
                setRevision((n) => n + 1);
              }}
            >
              重试
            </Button>
          }
        />
      )}
      {state.kind === "ready" && <DeclarationDetailBody detail={state.detail} />}
    </Dialog>
  );
}

export function DeclarationDetailHost() {
  const [params, setParams] = useSearchParams();
  const number = params.get("detail");
  return number ? (
    <DeclarationDetailDrawer
      key={number}
      number={number}
      onClose={() =>
        setParams(
          (current) => {
            const next = new URLSearchParams(current);
            next.delete("detail");
            return next;
          },
          { replace: true },
        )
      }
    />
  ) : null;
}
