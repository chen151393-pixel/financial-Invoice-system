import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { directDocumentGroupPath, directDocumentMergePath } from "../../../app/paths";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  DataTable,
  EmptyState,
  ErrorState,
  Field,
  FilterBar,
  Pagination,
  Skeleton,
  type Column,
} from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import { queryDirectDocuments } from "../api";
import { ensureSingleDocumentGroup } from "../api/document-group-api";
import type { DirectDocumentList, DirectDocumentQuery, DirectDocumentRow } from "../types";
import { DeclarationDetailLink } from "./DeclarationDetailLink";
import "./document-group.css";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; result: DirectDocumentList };
/** 单票资料入口：办理时确保一票一组；已有多票组在相邻的“多票资料组”查看。 */
export function DirectDocumentsPanel() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const initial: DirectDocumentQuery = {
    grouping: "single",
    keyword: "",
    consignee: params.get("consignee") || "",
    status: "all",
    page: 1,
    pageSize: 20,
  };
  const [query, setQuery] = useState(initial);
  const [state, setState] = useState<State>({ kind: "loading" });
  const [retry, setRetry] = useState(0);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const opening = useRef<AbortController | null>(null);
  useEffect(() => () => opening.current?.abort(), []);
  useEffect(() => {
    const abort = new AbortController();
    queryDirectDocuments(query, abort.signal)
      .then((result) => {
        if (!abort.signal.aborted) setState({ kind: "ready", result });
      })
      .catch((e: unknown) => {
        if (!abort.signal.aborted)
          setState({ kind: "error", message: e instanceof Error ? e.message : "读取失败" });
      });
    return () => abort.abort();
  }, [query, retry]);
  function update(next: DirectDocumentQuery) {
    setState({ kind: "loading" });
    setQuery(next);
  }
  async function open(row: DirectDocumentRow, merge = false) {
    if (busy || opening.current) return;
    const controller = new AbortController();
    opening.current = controller;
    setBusy(row.declarationNo);
    setError("");
    try {
      const group = await ensureSingleDocumentGroup(row.declarationNo, controller.signal);
      if (controller.signal.aborted) return;
      navigate(
        merge && group.kind === "single"
          ? directDocumentMergePath(row.declarationNo)
          : directDocumentGroupPath(group.id),
      );
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "资料组打开失败");
    } finally {
      opening.current = null;
      if (!controller.signal.aborted) setBusy("");
    }
  }
  const columns: Column<DirectDocumentRow>[] = [
    {
      key: "number",
      header: "报关单 / 销售订单",
      width: "240px",
      render: (r) => (
        <div className="settlement-cell">
          <strong>
            <DeclarationDetailLink number={r.declarationNo} />
          </strong>
          <span>{r.recordNo}</span>
          <span>{r.salesOrders.join("、")}</span>
        </div>
      ),
    },
    { key: "buyer", header: "境外收货人", render: (r) => r.consignee || "—" },
    { key: "seller", header: "NS 申报抬头", render: (r) => r.exportCompany || "—" },
    {
      key: "amount",
      header: "报关金额",
      align: "right",
      render: (r) => `${r.currency} ${r.amount ? money(r.amount) : "—"}`,
    },
    { key: "group", header: "资料组", render: (r) => r.groupNo || "首次办理时自动建组" },
    {
      key: "state",
      header: "资料进度",
      render: (r) => <Badge tone={r.status === "complete" ? "success" : "warning"}>{r.statusLabel}</Badge>,
    },
    {
      key: "actions",
      header: "操作",
      render: (r) => (
        <div className="settlement-cell">
          <div className="settlement-badges">
            <Button size="sm" disabled={!!busy} onClick={() => void open(r)}>
              {busy === r.declarationNo ? "正在打开…" : "办理资料"}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={!!busy || !r.edit.allowed}
              onClick={() => void open(r, true)}
            >
              合并办理
            </Button>
          </div>
          {!r.edit.allowed && <span>{r.edit.reason}</span>}
        </div>
      ),
    },
  ];
  return (
    <Card>
      <CardHeader
        title="报关资料 · 一票一组"
        description="每张报关单首次办理时自动建立单票资料组；共用提单时，从单票发起合并。"
      />
      <FilterBar
        embedded
        onSubmit={(form) => {
          const d = new FormData(form);
          update({
            ...query,
            keyword: String(d.get("keyword") || "").trim(),
            status: String(d.get("status") || "all") as DirectDocumentQuery["status"],
            page: 1,
          });
        }}
        actions={
          <>
            <Button type="submit" variant="primary">
              查询
            </Button>
            <Button type="reset" onClick={() => update(initial)}>
              重置
            </Button>
          </>
        }
      >
        <Field label="客户 / 报关单 / CD / 销售订单" grow>
          <input name="keyword" placeholder="输入关键词" />
        </Field>
        <Field label="资料进度">
          <select name="status" defaultValue="all">
            <option value="all">全部</option>
            <option value="pending_bill">待上传或核对提单</option>
            <option value="pending_contract">待生成或核对合同</option>
            <option value="stale">依据变化待更新</option>
            <option value="complete">资料齐全</option>
          </select>
        </Field>
      </FilterBar>
      {error && (
        <Alert tone="danger" title="资料组未打开">
          {error}
        </Alert>
      )}
      <CardContent flush>
        {query.consignee && (
          <Alert tone="info" title={`当前客户范围：${query.consignee}`}>
            <Button size="sm" onClick={() => update({ ...query, consignee: "", page: 1 })}>
              查看全部客户
            </Button>
          </Alert>
        )}
        {state.kind === "loading" && <Skeleton rows={4} label="正在读取报关资料" />}
        {state.kind === "error" && (
          <ErrorState
            title="报关资料读取失败"
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
        {state.kind === "ready" &&
          (state.result.items.length ? (
            <DataTable
              label="直接收汇单票资料"
              columns={columns}
              rows={state.result.items}
              rowKey={(r) => r.declarationNo}
              minWidth={1080}
            />
          ) : (
            <EmptyState
              title="没有符合条件的单票资料"
              description="已并入多票组的报关单在“多票资料组”中办理；可调整查询条件。"
            />
          ))}
      </CardContent>
      {state.kind === "ready" && state.result.total > 0 && (
        <CardFooter>
          <Pagination
            label="直接收汇单票资料分页"
            total={state.result.total}
            unit="票"
            page={state.result.page}
            pageCount={Math.max(1, Math.ceil(state.result.total / state.result.pageSize))}
            pageSize={query.pageSize}
            pageSizes={[20, 50]}
            onPageChange={(page) => update({ ...query, page })}
            onPageSizeChange={(pageSize) => update({ ...query, pageSize, page: 1 })}
          />
        </CardFooter>
      )}
    </Card>
  );
}
