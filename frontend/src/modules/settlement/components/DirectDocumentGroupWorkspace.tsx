import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { directDocumentGroupPath, directDocumentMergePath } from "../../../app/paths";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  ErrorState,
  Skeleton,
} from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import { getDocumentGroup } from "../api/document-group-api";
import type { DocumentGroup } from "../types/document-group";
import { BatchDocuments } from "./BatchDocuments";
import { DocumentGroupBasisDialog } from "./DocumentGroupBasisDialog";
import { DeclarationDetailLink } from "./DeclarationDetailLink";
import "./document-group.css";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; group: DocumentGroup };
export function DirectDocumentGroupWorkspace({
  id,
  onChanged,
  onLoaded,
}: {
  id: number;
  onChanged?: () => void;
  onLoaded?: (id: number, label: string) => void;
}) {
  const navigate = useNavigate();
  const [state, setState] = useState<State>({ kind: "loading" });
  const [refresh, setRefresh] = useState(0);
  const [updatingSource, setUpdatingSource] = useState(false);
  const target = useMemo(() => ({ groupId: id }), [id]);
  useEffect(() => {
    const abort = new AbortController();
    getDocumentGroup(id, abort.signal)
      .then((group) => {
        if (abort.signal.aborted) return;
        if (group.id !== id) {
          navigate(directDocumentGroupPath(group.id), { replace: true });
          return;
        }
        setState({ kind: "ready", group });
        onLoaded?.(group.id, group.groupNo);
      })
      .catch((e: unknown) => {
        if (!abort.signal.aborted)
          setState({ kind: "error", message: e instanceof Error ? e.message : "资料组读取失败" });
      });
    return () => abort.abort();
  }, [id, refresh, navigate, onLoaded]);
  if (state.kind === "loading") return <Skeleton rows={4} label="正在打开资料组" />;
  if (state.kind === "error")
    return (
      <ErrorState
        title="资料组读取失败"
        message={state.message}
        action={
          <Button
            onClick={() => {
              setState({ kind: "loading" });
              setRefresh((n) => n + 1);
            }}
          >
            重试
          </Button>
        }
      />
    );
  const group = state.group;
  return (
    <div className="settlement-page settlement-group-workspace">
      <Card>
        <CardHeader
          title={
            <span className="settlement-group-workspace__identity">
              {group.groupNo}
              <Badge>直接收汇</Badge>
              <Badge tone="info">{group.kind === "single" ? "一票一组" : "多票资料组"}</Badge>
              <Badge tone={group.status === "complete" ? "success" : "warning"}>{group.statusLabel}</Badge>
            </span>
          }
          description={`${group.consignee} · ${group.currency} ${money(group.amount)} · ${group.members.length} 张报关单`}
          actions={
            <>
              {group.merge.allowed && (
                <Link
                  className="ui-button ui-button--secondary"
                  to={directDocumentMergePath(group.members[0].declarationNo)}
                >
                  与其他报关单合并办理
                </Link>
              )}
              {group.package.allowed ? (
                <a className="ui-button ui-button--secondary" href={group.packageUrl} download>
                  下载资料包
                </a>
              ) : (
                <Button disabled title={group.package.reason}>
                  下载资料包
                </Button>
              )}
            </>
          }
        />
      </Card>
      {!group.edit.allowed && (
        <Alert tone="danger" title="来源需要核对">
          <p>{group.edit.reason}</p>
          {group.updateSource?.allowed ? (
            <Button onClick={() => setUpdatingSource(true)}>核对并更新来源</Button>
          ) : (
            <p>{group.updateSource?.reason}</p>
          )}
        </Alert>
      )}
      {updatingSource && (
        <DocumentGroupBasisDialog
          id={id}
          onClose={() => setUpdatingSource(false)}
          onSaved={(updated) => {
            setUpdatingSource(false);
            setState({ kind: "ready", group: updated });
            setRefresh((n) => n + 1);
            onChanged?.();
          }}
        />
      )}
      <BatchDocuments
        key={`${id}-${group.consignee}-${group.currency}`}
        target={target}
        onChanged={() => {
          setRefresh((n) => n + 1);
          onChanged?.();
        }}
        overview={(documents) => (
          <Card>
            <CardHeader
              title="组内报关单 · 原件"
              actions={
                <span>
                  合计 {group.currency} {money(group.amount)}
                </span>
              }
            />
            <CardContent flush>
              <div className="settlement-group-members">
                {group.members.map((member) => {
                  const file = documents.declarationFiles.find(
                    (f) => f.declarationNo === member.declarationNo,
                  );
                  return (
                    <div key={member.declarationNo} className="settlement-group-member">
                      <div>
                        <DeclarationDetailLink number={member.declarationNo} />
                        <p>
                          {member.exportCompany || "申报抬头待核对"} · 出口 {member.exportDate || "日期待补"}
                        </p>
                      </div>
                      <div>
                        <strong>
                          {member.currency} {member.amount ? money(member.amount) : "—"}
                        </strong>
                        <Badge tone={file?.archived ? "success" : "warning"}>
                          {file?.archived ? "已归档" : file?.statusLabel || "未归档"}
                        </Badge>
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        )}
      />
    </div>
  );
}
