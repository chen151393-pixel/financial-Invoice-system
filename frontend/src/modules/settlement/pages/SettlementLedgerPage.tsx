import { useEffect, useState } from "react";
import { Navigate, useSearchParams } from "react-router";
import { directDocumentGroupPath } from "../../../app/paths";
import { DirectDocumentGroupsPanel } from "../components/DirectDocumentGroupsPanel";
import { DirectDocumentEntry } from "../components/DirectDocumentEntry";
import { useNavigate } from "react-router";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  EmptyState,
  ErrorState,
  Field,
  FilterBar,
  Pagination,
  Skeleton,
  StatCard,
  StatGrid,
  Tabs,
} from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import { queryLedger } from "../api";
import { DirectDocumentsPanel } from "../components/DirectDocumentsPanel";
import { LedgerSummaryTable } from "../components/LedgerGroupTable";
import type { LedgerList, LedgerQuery, LedgerStatusFilter } from "../types";
import "../components/settlement.css";

type State = { kind: "loading" } | { kind: "ready"; result: LedgerList } | { kind: "error"; message: string };

const INITIAL: LedgerQuery = {
  consignee: "",
  company: "",
  byRecipient: true,
  status: "all",
  page: 1,
  pageSize: 20,
};

/**
 * 直接收汇明细（总账）：按境外收货人、收款人和币种汇总对账期间金额。
 * 余额、状态与合计全部来自后端；本页不做任何金额计算。
 */
const VIEWS = [
  { key: "ledger", label: "客户总账" },
  { key: "documents", label: "报关资料" },
  { key: "groups", label: "多票资料组" },
] as const;

export function SettlementLedgerPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const view =
    params.get("tab") === "groups" ||
    (params.get("tab") === "documents" && params.get("documentView") === "groups")
      ? "groups"
      : params.get("tab") === "documents"
        ? "documents"
        : "ledger";
  const legacyGroupId = Number(params.get("groupId")) || null;
  const entryNumber = params.get("declarationNo") || "";
  const [query, setQuery] = useState<LedgerQuery>(() => ({
    ...INITIAL,
    consignee: params.get("consignee") || "",
  }));
  const [state, setState] = useState<State>({ kind: "loading" });
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setState({ kind: "loading" });
      try {
        setState({ kind: "ready", result: await queryLedger(query, controller.signal) });
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") return;
        setState({ kind: "error", message: error instanceof Error ? error.message : "加载失败，请稍后重试" });
      }
    }
    void load();
    return () => controller.abort();
  }, [query, refresh]);

  return (
    <div className="settlement-page">
      {state.kind === "ready" &&
        state.result.totals.map((total) => (
          <StatGrid key={total.currency} label={`${total.currency} 收汇概况`}>
            <StatCard
              glyph="初"
              label={`期初差额（${total.currency}）`}
              value={money(total.openingBalance)}
            />
            <StatCard
              glyph="出"
              label={`本期出口（${total.currency}）`}
              value={money(total.exportTotal)}
              note={`${total.exportCount} 票报关单`}
            />
            <StatCard
              glyph="收"
              tone="primary"
              label={`本期收汇（${total.currency}）`}
              value={money(total.receiptTotal)}
              note={`${total.receiptCount} 笔银行收汇`}
            />
            <StatCard
              glyph="余"
              tone="warning"
              label={`期末差额（${total.currency}）`}
              value={money(total.balance)}
              note={`未收 ${money(total.outstanding)} · 超收 ${money(total.overpaid)}`}
            />
          </StatGrid>
        ))}
      <Tabs
        label="直接收汇工作区"
        items={VIEWS}
        value={view}
        onChange={(next) => {
          const values = new URLSearchParams(params);
          values.delete("declarationNo");
          values.delete("groupId");
          values.delete("documentView");
          if (next === "ledger") values.delete("tab");
          else values.set("tab", next);
          setParams(values);
        }}
      />
      {legacyGroupId && <Navigate to={directDocumentGroupPath(legacyGroupId)} replace />}
      {view === "documents" &&
        (entryNumber ? <DirectDocumentEntry number={entryNumber} /> : <DirectDocumentsPanel />)}
      {view === "groups" && (
        <DirectDocumentGroupsPanel
          consignee={params.get("consignee") || ""}
          refresh={0}
          onSelect={(id) => navigate(directDocumentGroupPath(id))}
        />
      )}
      <div hidden={view !== "ledger"}>
        <Card>
          <CardHeader
            title="直接收汇明细"
            description="按境外收货人和收款抬头对账，出口计入出口日期，收汇计入实际到账日期。"
          />
          <FilterBar
            embedded
            onSubmit={(form) => {
              const data = new FormData(form);
              setQuery({
                ...query,
                consignee: String(data.get("consignee") || "").trim(),
                receivingCompany: String(data.get("receivingCompany") || "").trim(),
                startDate: String(data.get("startDate") || "") || null,
                endDate: String(data.get("endDate") || "") || null,
                status: String(data.get("status") || "all") as LedgerStatusFilter,
                page: 1,
              });
            }}
            actions={
              <>
                <Button type="submit" variant="primary">
                  查询
                </Button>
                <Button type="reset" onClick={() => setQuery(INITIAL)}>
                  清空
                </Button>
              </>
            }
          >
            <Field label="境外收货人" grow>
              <input name="consignee" placeholder="按名称搜索" defaultValue={query.consignee} />
            </Field>
            <Field label="收款人（收汇抬头）" grow>
              <input name="receivingCompany" placeholder="按收款抬头搜索" />
            </Field>
            <Field label="对账开始日">
              <input type="date" name="startDate" />
            </Field>
            <Field label="对账结束日">
              <input type="date" name="endDate" />
            </Field>
            <Field label="期末差额">
              <select name="status" defaultValue={INITIAL.status}>
                <option value="all">全部</option>
                <option value="outstanding">有未收</option>
                <option value="settled">已收齐</option>
                <option value="overpaid">超收</option>
              </select>
            </Field>
          </FilterBar>
          <CardContent flush>
            {state.kind === "loading" && <Skeleton rows={5} label="正在读取直接收汇明细" />}
            {state.kind === "error" && (
              <ErrorState
                title="直接收汇明细读取失败"
                message={state.message}
                action={<Button onClick={() => setRefresh((n) => n + 1)}>重试</Button>}
              />
            )}
            {state.kind === "ready" && (
              <>
                {state.result.skipped.length > 0 && (
                  <Alert tone="warning" title={`${state.result.skipped.length} 张直接收汇报关单未计入`}>
                    {state.result.skipped.map((item) => `${item.declarationNo}（${item.reason}）`).join("；")}
                  </Alert>
                )}
                {state.result.groups.length ? (
                  <LedgerSummaryTable groups={state.result.groups} />
                ) : (
                  <EmptyState
                    title="没有符合条件的直接收汇明细"
                    description="判定为直接收汇的报关单和银行收汇明细中的收汇记录出现在这里。"
                  />
                )}
              </>
            )}
          </CardContent>
          {state.kind === "ready" && state.result.total > 0 && (
            <CardFooter>
              <Pagination
                label="直接收汇明细分页"
                total={state.result.total}
                unit="组"
                page={state.result.page}
                pageCount={Math.max(1, Math.ceil(state.result.total / state.result.pageSize))}
                pageSize={query.pageSize}
                pageSizes={[20, 50]}
                onPageChange={(page) => setQuery({ ...query, page })}
                onPageSizeChange={(pageSize) => setQuery({ ...query, pageSize, page: 1 })}
              />
            </CardFooter>
          )}
        </Card>
      </div>
    </div>
  );
}
