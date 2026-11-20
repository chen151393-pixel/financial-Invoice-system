import { useMemo, useState } from "react";
import { useSearchParams, useLocation, useNavigate } from "react-router";
import { settlementHkRegistrationPath } from "../../../app/paths";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  FilterBar,
  Pagination,
  Skeleton,
  StatCard,
  StatGrid,
} from "../../../shared/components/ui";
import { HkBatchCard } from "../components/HkBatchCard";
import { HkPendingPanel } from "../components/HkPendingPanel";
import { exportHkWorkbench } from "../api/hk-workbench-api";
import { Alert } from "../../../shared/components/ui";
import { useHkWorkbench } from "../hooks/useHkWorkbench";
import type { HkPending, HkStageKey } from "../types/hk-workbench";
import "../components/hk-workbench.css";
const VALID_STAGES: HkStageKey[] = [
  "open",
  "register",
  "collected",
  "documents_ready",
  "settled",
  "cancelled",
  "all",
];
const GLYPHS: Partial<Record<HkStageKey, string>> = {
  open: "进",
  register: "登",
  collected: "资",
  documents_ready: "汇",
  settled: "完",
};
const TITLES: Record<HkStageKey, string> = {
  open: "进行中的批次",
  register: "待登记香港回款",
  collected: "香港已收 · 办理资料",
  documents_ready: "资料已出 · 待汇回",
  settled: "已结汇批次",
  cancelled: "已作废批次",
  all: "全部批次",
};
const pageNumber = (value: string | null) =>
  value && /^\d+$/.test(value) && Number(value) > 0 ? Number(value) : 1;

/** 香港中转：阶段入口 → 待登记报关单 → 批次卡片内办理资料与汇回。 */
export function SettlementHkTransitPage() {
  const [params, setParams] = useSearchParams();
  const value =
    params.get("stage") ||
    (params.get("tab") === "receipts"
      ? "register"
      : params.get("batchNo") || params.get("consignee")
        ? "all"
        : "open");
  const stage = VALID_STAGES.includes(value as HkStageKey) ? (value as HkStageKey) : "open";
  const consignee = params.get("consignee") || "";
  const keyword = params.get("keyword") || params.get("batchNo") || "";
  const page = pageNumber(params.get("page"));
  const pendingPage = pageNumber(params.get("pendingPage"));
  const pageSize = [10, 20, 50].includes(pageNumber(params.get("pageSize")))
    ? pageNumber(params.get("pageSize"))
    : 10;
  const pendingPageSize = [20, 50, 100].includes(pageNumber(params.get("pendingPageSize")))
    ? pageNumber(params.get("pendingPageSize"))
    : 20;
  const query = useMemo(
    () => ({ stage, consignee, keyword, page, pendingPage, pageSize, pendingPageSize }),
    [stage, consignee, keyword, page, pendingPage, pageSize, pendingPageSize],
  );
  const { state, reload } = useHkWorkbench(query);
  const location = useLocation();
  const navigate = useNavigate();
  const navigationState = location.state as { hkReceiptDraftId?: string; hkSelection?: HkPending[] } | null;
  const [selected, setSelected] = useState<HkPending[]>(navigationState?.hkSelection || []);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  async function download() {
    setExporting(true);
    setExportError("");
    try {
      const report = await exportHkWorkbench(query);
      const url = URL.createObjectURL(new Blob([report.content], { type: "text/csv;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = report.fileName;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "导出失败");
    } finally {
      setExporting(false);
    }
  }
  function update(values: Record<string, string>) {
    const next = new URLSearchParams(params);
    next.delete("tab");
    next.delete("batchNo");
    for (const [key, text] of Object.entries(values)) {
      if (text) next.set(key, text);
      else next.delete(key);
    }
    setParams(next);
  }
  function changeStage(next: HkStageKey) {
    setSelected([]);
    update({ stage: next, page: "", pendingPage: "" });
  }
  const result = state.kind === "ready" ? state.result : null;
  return (
    <div className="settlement-page settlement-hk-workbench">
      {result ? (
        <StatGrid label="香港中转处理阶段" min={170}>
          {result.stages.map((item) => (
            <StatCard
              key={item.key}
              compact
              glyph={GLYPHS[item.key] || "批"}
              tone={item.tone}
              label={item.label}
              value={item.value}
              note={item.note}
              selected={stage === item.key}
              onSelect={() => changeStage(item.key)}
            />
          ))}
        </StatGrid>
      ) : state.kind === "loading" ? (
        <Skeleton rows={2} label="正在读取香港中转阶段" />
      ) : null}
      <Card>
        <FilterBar
          key={`${consignee}:${keyword}:${stage}`}
          embedded
          onSubmit={(form) => {
            const data = new FormData(form);
            setSelected([]);
            update({
              consignee: String(data.get("consignee") || "").trim(),
              keyword: String(data.get("keyword") || "").trim(),
              page: "",
              pendingPage: "",
            });
          }}
          actions={
            <>
              <Button type="submit" variant="primary">
                查询
              </Button>
              <Button
                type="button"
                onClick={() => {
                  setSelected([]);
                  setParams({});
                }}
              >
                重置
              </Button>
              <Button type="button" onClick={reload}>
                刷新
              </Button>
              <Button type="button" disabled={exporting} onClick={() => void download()}>
                {exporting ? "正在导出…" : "导出"}
              </Button>
            </>
          }
        >
          <Field label="境外收货人" grow>
            <input name="consignee" defaultValue={consignee} placeholder="按香港收货人筛选" />
          </Field>
          <Field label="批次号 / 报关单号 / 流水号" grow>
            <input name="keyword" defaultValue={keyword} placeholder="输入编号或流水号" />
          </Field>
          <Field label="查看范围">
            <select
              aria-label="香港中转查看范围"
              value={stage}
              onChange={(event) => changeStage(event.target.value as HkStageKey)}
            >
              {VALID_STAGES.map((key) => (
                <option key={key} value={key}>
                  {TITLES[key]}
                </option>
              ))}
            </select>
          </Field>
        </FilterBar>
      </Card>
      {exportError && <Alert tone="danger">{exportError}</Alert>}
      {state.kind === "loading" && <Skeleton rows={5} label="正在读取香港中转工作区" />}
      {state.kind === "error" && (
        <ErrorState
          title="香港中转工作区读取失败"
          message={state.message}
          action={<Button onClick={reload}>重试</Button>}
        />
      )}
      {result && (
        <>
          {(stage === "open" || stage === "register" || stage === "all") && (
            <HkPendingPanel
              rows={result.pending}
              total={result.pendingTotal}
              page={result.pendingPage}
              pageCount={result.pendingPageCount}
              pageSize={query.pendingPageSize}
              onPageSizeChange={(size) => update({ pendingPageSize: String(size), pendingPage: "" })}
              selected={selected.map((row) => row.declarationNo)}
              onToggle={(row) =>
                setSelected((current) =>
                  current.some((item) => item.declarationNo === row.declarationNo)
                    ? current.filter((item) => item.declarationNo !== row.declarationNo)
                    : [...current, row],
                )
              }
              onToggleAll={() => {
                const selectable = result.pending.filter((row) => row.select.allowed);
                const all = selectable.every((row) =>
                  selected.some((item) => item.declarationNo === row.declarationNo),
                );
                setSelected((current) =>
                  all
                    ? current.filter(
                        (row) => !selectable.some((item) => item.declarationNo === row.declarationNo),
                      )
                    : [
                        ...current.filter(
                          (row) => !selectable.some((item) => item.declarationNo === row.declarationNo),
                        ),
                        ...selectable,
                      ],
                );
              }}
              onPageChange={(next) => update({ pendingPage: String(next) })}
              onRegister={() =>
                navigate(
                  settlementHkRegistrationPath(
                    selected.map((row) => row.declarationNo),
                    navigationState?.hkReceiptDraftId || crypto.randomUUID(),
                  ),
                  { state: { hkReturnTo: location.pathname + location.search } },
                )
              }
            />
          )}
          {stage !== "register" && (
            <section aria-label={TITLES[stage]} className="settlement-hk-batches">
              {result.batches.map((row) => (
                <HkBatchCard key={row.batch.id} row={row} onChanged={reload} />
              ))}
              {!result.batches.length && (
                <EmptyState
                  title="没有符合条件的批次"
                  description="可切换处理阶段，或勾选待登记报关单建立香港到账批次。"
                />
              )}
              {result.batchTotal > 0 && (
                <Pagination
                  label="香港中转批次分页"
                  total={result.batchTotal}
                  unit="批"
                  page={result.page}
                  pageCount={result.pageCount}
                  pageSize={query.pageSize}
                  pageSizes={[10, 20, 50]}
                  onPageSizeChange={(size) => update({ pageSize: String(size), page: "" })}
                  onPageChange={(next) => update({ page: String(next) })}
                />
              )}
            </section>
          )}
        </>
      )}
      <details className="settlement-hk-rules">
        <summary>办理规则与统计口径</summary>
        <p>
          登记回款的报关单须属于同一香港境外收货人、同一币种，且未被其他有效批次占用。到账与手续费合计对平、提单字段与合同齐全后，才可确认资料已出；报关原件未归档仅提示。资料已出后登记汇回，汇回与手续费合计对平后结汇。待汇回超过
          30 天提示跟进。已结汇显示累计批次。
        </p>
      </details>
    </div>
  );
}
