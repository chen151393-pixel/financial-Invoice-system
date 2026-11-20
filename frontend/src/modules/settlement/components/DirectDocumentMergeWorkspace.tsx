import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { directDocumentGroupPath, settlementDirectDocumentsPath } from "../../../app/paths";
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
} from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import {
  confirmDocumentMergeRecovering,
  MergeResultUnknown,
  previewDocumentMerge,
  queryDocumentMerge,
} from "../api/document-merge-api";
import type {
  ConfirmMerge,
  DocumentMergeQuery,
  MergeCandidate,
  MergeCandidates,
  MergePreview,
} from "../types/document-merge";
import "./document-group.css";

type Result<T> = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; value: T };
export function DirectDocumentMergeWorkspace({ source }: { source: string }) {
  const navigate = useNavigate();
  const initial: DocumentMergeQuery = {
    sourceDeclarationNo: source,
    keyword: "",
    exportFrom: null,
    exportTo: null,
    page: 1,
    pageSize: 20,
  };
  const [query, setQuery] = useState(initial);
  const [candidates, setCandidates] = useState<Result<MergeCandidates>>({ kind: "loading" });
  const [selection, setSelection] = useState<string[]>([source]);
  const [sharedBillId, setSharedBillId] = useState<number | null>(null);
  const [preview, setPreview] = useState<Result<MergePreview>>({ kind: "loading" });
  const [retry, setRetry] = useState(0);
  const [candidateRetry, setCandidateRetry] = useState(0);
  const [requestId] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState<ConfirmMerge | null>(null);
  const submitting = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const locked = busy || attempt !== null;
  useEffect(() => {
    if (!source) return;
    const abort = new AbortController();
    queryDocumentMerge(query, abort.signal)
      .then((value) => {
        if (!abort.signal.aborted) setCandidates({ kind: "ready", value });
      })
      .catch((e: unknown) => {
        if (!abort.signal.aborted)
          setCandidates({ kind: "error", message: e instanceof Error ? e.message : "候选报关单读取失败" });
      });
    return () => abort.abort();
  }, [source, query, candidateRetry]);
  useEffect(() => {
    if (!source) return;
    const abort = new AbortController();
    previewDocumentMerge(
      { sourceDeclarationNo: source, declarationNos: selection, sharedBillId },
      abort.signal,
    )
      .then((value) => {
        if (!abort.signal.aborted) setPreview({ kind: "ready", value });
      })
      .catch((e: unknown) => {
        if (!abort.signal.aborted)
          setPreview({ kind: "error", message: e instanceof Error ? e.message : "合并条件核对失败" });
      });
    return () => abort.abort();
  }, [source, selection, sharedBillId, retry]);
  function update(next: DocumentMergeQuery) {
    setCandidates({ kind: "loading" });
    setQuery(next);
  }
  function toggle(row: MergeCandidate) {
    setPreview({ kind: "loading" });
    setSelection((current) =>
      current.includes(row.declarationNo)
        ? current.filter((n) => n !== row.declarationNo)
        : [...current, row.declarationNo],
    );
  }
  function remove(number: string) {
    setPreview({ kind: "loading" });
    setSelection((current) => current.filter((n) => n !== number));
  }
  async function merge() {
    if (submitting.current || (!attempt && (preview.kind !== "ready" || !preview.value.merge.allowed)))
      return;
    const body =
      attempt ||
      (preview.kind === "ready"
        ? {
            sourceDeclarationNo: source,
            declarationNos: selection,
            sharedBillId: preview.value.sharedBillId,
            requestId,
            previewToken: preview.value.token,
          }
        : null);
    if (!body) return;
    submitting.current = true;
    setAttempt(body);
    setBusy(true);
    setError("");
    try {
      const group = await confirmDocumentMergeRecovering(body);
      if (mounted.current) navigate(directDocumentGroupPath(group.id), { replace: true });
    } catch (e) {
      if (!mounted.current) return;
      setError(e instanceof Error ? e.message : "暂时无法确认合并结果");
      if (!(e instanceof MergeResultUnknown)) {
        setAttempt(null);
        setPreview({ kind: "loading" });
        setCandidates({ kind: "loading" });
        setRetry((n) => n + 1);
        setCandidateRetry((n) => n + 1);
      }
    } finally {
      submitting.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  if (!source)
    return (
      <EmptyState
        title="请先选择本单"
        description="从报关资料打开单票资料组，再发起合并。"
        action={<Link to={settlementDirectDocumentsPath()}>返回报关资料</Link>}
      />
    );
  const sourceRow = candidates.kind === "ready" ? candidates.value.source : null;
  return (
    <div className="settlement-merge">
      <div className="settlement-merge__main">
        <Card>
          <CardHeader
            title="选择一起办理资料的报关单"
            description="本单固定选中；候选为同一境外收货人、同币种的直接收汇报关单，不限制申报抬头。"
          />
          <FilterBar
            embedded
            onSubmit={(form) => {
              const d = new FormData(form);
              update({
                ...query,
                keyword: String(d.get("keyword") || "").trim(),
                exportFrom: String(d.get("exportFrom") || "") || null,
                exportTo: String(d.get("exportTo") || "") || null,
                page: 1,
              });
            }}
            actions={
              <>
                <Button type="submit" variant="primary" disabled={locked}>
                  查询
                </Button>
                <Button type="reset" disabled={locked} onClick={() => update(initial)}>
                  重置
                </Button>
              </>
            }
          >
            <Field label="报关单 / CD / 销售订单 / 申报抬头" grow>
              <input name="keyword" placeholder="输入关键词" disabled={locked} />
            </Field>
            <Field label="出口日期从">
              <input type="date" name="exportFrom" disabled={locked} />
            </Field>
            <Field label="至">
              <input type="date" name="exportTo" disabled={locked} />
            </Field>
          </FilterBar>
          <CardContent>
            {candidates.kind === "loading" && <Skeleton rows={4} label="正在读取可合并报关单" />}
            {candidates.kind === "error" && (
              <ErrorState
                title="候选报关单读取失败"
                message={candidates.message}
                action={
                  <Button
                    onClick={() => {
                      setCandidates({ kind: "loading" });
                      setCandidateRetry((n) => n + 1);
                    }}
                  >
                    重试
                  </Button>
                }
              />
            )}
            {candidates.kind === "ready" && (
              <div className="settlement-merge__choices">
                {!candidates.value.items.some((r) => r.source) && (
                  <MergeChoice row={candidates.value.source} checked busy={locked} onChange={() => {}} />
                )}
                {candidates.value.items.map((row) => (
                  <MergeChoice
                    key={row.declarationNo}
                    row={row}
                    checked={selection.includes(row.declarationNo)}
                    busy={locked}
                    onChange={() => toggle(row)}
                  />
                ))}
                {!candidates.value.items.some((row) => !row.source) && (
                  <EmptyState
                    title="当前条件下没有其他报关单"
                    description="本单仍保留，调整查询条件后继续勾选。"
                  />
                )}
              </div>
            )}
          </CardContent>
          {candidates.kind === "ready" && candidates.value.total > 0 && (
            <CardFooter>
              <Pagination
                label="合并候选分页"
                total={candidates.value.total}
                unit="票"
                page={candidates.value.page}
                pageCount={Math.max(1, Math.ceil(candidates.value.total / candidates.value.pageSize))}
                pageSize={query.pageSize}
                pageSizes={[20, 50]}
                onPageChange={(page) => update({ ...query, page })}
                onPageSizeChange={(pageSize) => update({ ...query, pageSize, page: 1 })}
              />
            </CardFooter>
          )}
        </Card>
        {preview.kind === "ready" && (
          <Card>
            <CardHeader
              title="合并后的资料变化"
              description="原提单和合同记录保留在新组；合同按组内最新范围重新生成。"
            />
            <CardContent>
              <p>
                已有提单 {preview.value.existingBillCount} 份、合同 {preview.value.existingContractCount}{" "}
                份；预计按申报抬头与销售订单生成 {preview.value.contracts.length} 份合同。
              </p>
              <Field label="合并后共用的本单提单">
                <select
                  value={preview.value.sharedBillId}
                  disabled={locked}
                  onChange={(e) => {
                    setPreview({ kind: "loading" });
                    setSharedBillId(Number(e.currentTarget.value));
                  }}
                >
                  <option value={0}>暂不指定，合并后上传或核对</option>
                  {preview.value.sourceBills.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.blNo || b.fileName}
                    </option>
                  ))}
                </select>
              </Field>
              <DataTable
                label="合并后预计合同"
                rows={preview.value.contracts}
                rowKey={(r) => r.key}
                minWidth={520}
                columns={[
                  { key: "number", header: "销售订单", render: (r) => r.contractNo },
                  { key: "seller", header: "卖方（NS 申报抬头）", render: (r) => r.sellerName || "待核对" },
                  { key: "scope", header: "覆盖报关单", render: (r) => r.declarationNos.join("、") },
                  {
                    key: "amount",
                    header: "预计合同金额",
                    align: "right",
                    render: (r) => `${r.currency} ${money(r.amount)}`,
                  },
                ]}
              />
              <details>
                <summary>查看已选报关单（跨页保留）</summary>
                <div className="settlement-group-selection">
                  {preview.value.selected.map((r) => (
                    <Button
                      key={r.declarationNo}
                      size="sm"
                      disabled={locked || r.declarationNo === source}
                      onClick={() => remove(r.declarationNo)}
                    >
                      {r.declarationNo === source ? "本单 " : "移除 "}
                      {r.declarationNo}
                    </Button>
                  ))}
                </div>
              </details>
            </CardContent>
          </Card>
        )}
      </div>
      <aside className="settlement-merge__aside" aria-label="合并条件确认">
        <Card>
          <CardHeader title="合并条件" />
          <CardContent>
            {preview.kind === "loading" && <Skeleton rows={5} label="正在核对合并条件" />}
            {preview.kind === "error" && (
              <ErrorState
                title="合并条件核对失败"
                message={preview.message}
                action={
                  <Button
                    onClick={() => {
                      setPreview({ kind: "loading" });
                      setRetry((n) => n + 1);
                    }}
                  >
                    重试
                  </Button>
                }
              />
            )}
            {preview.kind === "ready" && (
              <>
                <div className="settlement-merge__total">
                  <span>已选 {preview.value.selectedCount} 票 · 报关合计</span>
                  <strong>
                    {preview.value.currency} {preview.value.amount ? money(preview.value.amount) : "—"}
                  </strong>
                </div>
                <ul className="settlement-merge__checks">
                  {preview.value.checks.map((check) => (
                    <li key={check.key}>
                      <Badge tone={check.passed ? "success" : "warning"}>
                        {check.passed ? "通过" : "待核对"}
                      </Badge>
                      <div>
                        <strong>{check.label}</strong>
                        <p>{check.detail}</p>
                      </div>
                    </li>
                  ))}
                </ul>
                <Button
                  variant="primary"
                  disabled={busy || (!attempt && !preview.value.merge.allowed)}
                  onClick={() => void merge()}
                >
                  {busy ? "正在确认合并结果…" : attempt ? "按原请求重试" : "创建资料组并合并"}
                </Button>
                {!preview.value.merge.allowed && (
                  <p className="settlement-form__hint">{preview.value.merge.reason}</p>
                )}
              </>
            )}
            {error && (
              <Alert
                tone={attempt ? "warning" : "danger"}
                title={attempt ? "合并结果待确认" : "资料组未合并"}
              >
                {error}
              </Alert>
            )}
            <p className="settlement-form__hint">创建成功后进入新资料组，原单票组链接自动指向新组。</p>
            <Link
              to={
                sourceRow?.groupId
                  ? directDocumentGroupPath(sourceRow.groupId)
                  : settlementDirectDocumentsPath("", source)
              }
            >
              取消，返回本单资料
            </Link>
          </CardContent>
          <CardFooter>资料组只管理资料，不改变收款推算和结汇状态。</CardFooter>
        </Card>
      </aside>
    </div>
  );
}
function MergeChoice({
  row,
  checked,
  busy,
  onChange,
}: {
  row: MergeCandidate;
  checked: boolean;
  busy: boolean;
  onChange: () => void;
}) {
  return (
    <label className="settlement-merge-choice" data-selected={checked}>
      <input
        type="checkbox"
        aria-label={`选择合并 ${row.declarationNo}`}
        checked={checked}
        disabled={busy || row.source || (!row.select.allowed && !checked)}
        onChange={onChange}
      />
      <span className="settlement-merge-choice__body">
        <span className="settlement-merge-choice__title">
          <strong>{row.declarationNo}</strong>
          {row.source ? (
            <Badge tone="info">本单</Badge>
          ) : row.sharedBill ? (
            <Badge tone="success">已有相同提单</Badge>
          ) : row.groupNo ? (
            <Badge>{row.groupNo}</Badge>
          ) : (
            <Badge>首次办理时建组</Badge>
          )}
        </span>
        <span className="settlement-form__hint">
          {row.consignee} · 出口 {row.exportDate || "日期待补"} · {row.exportCompany || "申报抬头待核对"} ·
          销售订单 {row.salesOrders.join("、") || "待核对"}
        </span>
        {!row.select.allowed && <span className="settlement-form__hint">{row.select.reason}</span>}
      </span>
      <strong className="settlement-merge-choice__amount">
        {row.currency} {row.amount ? money(row.amount) : "—"}
      </strong>
    </label>
  );
}
