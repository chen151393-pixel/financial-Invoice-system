import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { matchingInvoicePath } from "../../../app/paths";
import {
  Alert,
  Card,
  CardFooter,
  CardHeader,
  EmptyState,
  Pagination,
  Skeleton,
} from "../../../shared/components/ui";
import { openLocalSession } from "../../identity/api";
import {
  getInvoiceTotals,
  getMatchingSummaries,
  type InvoiceTotals,
  type MatchingSummary,
} from "../../matching/api";
import { getInvoice, getInvoiceStats, listInvoices } from "../api/invoice";
import { emptyFilters, InvoiceFilters } from "../components/InvoiceFilters";
import { InvoiceCharts } from "../components/InvoiceCharts";
import { InvoiceDetailDrawer } from "../components/InvoiceDetailDrawer";
import { InvoiceSummary } from "../components/InvoiceSummary";
import { InvoiceTable } from "../components/InvoiceTable";
import { InvoiceDetailRefresh } from "../components/InvoiceDetailRefresh";
import { useDetailRefresh } from "../hooks/useDetailRefresh";
import { useInvoiceAccounts } from "../hooks/useInvoiceAccounts";
import type { InvoiceDetail, InvoiceListResult, InvoiceStats } from "../types/invoice";
import "./invoice-list.css";

type Query = typeof emptyFilters & { page: number; pageSize: number; version: number };

export function InvoiceListPage() {
  const navigate = useNavigate();
  const [draft, setDraft] = useState(emptyFilters);
  const [query, setQuery] = useState<Query>({ ...emptyFilters, page: 1, pageSize: 20, version: 0 });
  const [data, setData] = useState<InvoiceListResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [matching, setMatching] = useState<Record<string, MatchingSummary>>({});
  const [matchingError, setMatchingError] = useState("");
  const [totals, setTotals] = useState<InvoiceTotals | null>(null);
  const [totalsLoading, setTotalsLoading] = useState(true);
  const [totalsError, setTotalsError] = useState("");
  const [stats, setStats] = useState<InvoiceStats | null>(null);
  const [statsError, setStatsError] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<InvoiceDetail | null>(null);
  const [detailError, setDetailError] = useState("");
  const accounts = useInvoiceAccounts(query.version);

  function updateQuery(next: Query) {
    setLoading(true);
    setError("");
    setSelected(null);
    setData(null);
    setMatching({});
    setMatchingError("");
    setTotals(null);
    setTotalsLoading(true);
    setTotalsError("");
    setStats(null);
    setStatsError("");
    setQuery(next);
  }
  const refresh = () => updateQuery({ ...query, version: query.version + 1 });
  const detailRefresh = useDetailRefresh(data?.rows.map((row) => row.id) ?? [], refresh);
  function changeQuery(next: Query) {
    detailRefresh.clearSelection();
    updateQuery(next);
  }

  useEffect(() => {
    // 浏览器返回缓存页时重新查询，避免显示过期的比对状态。
    function restore(event: PageTransitionEvent) {
      if (!event.persisted) return;
      setMatching({});
      setData(null);
      setLoading(true);
      setTotals(null);
      setTotalsLoading(true);
      setTotalsError("");
      setQuery((current) => ({ ...current, version: current.version + 1 }));
    }
    window.addEventListener("pageshow", restore);
    return () => window.removeEventListener("pageshow", restore);
  }, []);

  useEffect(() => {
    let active = true;
    async function loadTotals() {
      try {
        const response = await getInvoiceTotals(query);
        if (active) setTotals(response);
      } catch (reason) {
        if (active) setTotalsError(reason instanceof Error ? reason.message : "金额统计读取失败");
      } finally {
        if (active) setTotalsLoading(false);
      }
    }
    // 分布图与列表同一筛选条件（不含分页）
    async function loadStats(filters: URLSearchParams) {
      try {
        const response = await getInvoiceStats(filters);
        if (active) setStats(response);
      } catch (reason) {
        if (active) setStatsError(reason instanceof Error ? reason.message : "发票分布读取失败");
      }
    }
    async function load() {
      let totalsStarted = false;
      try {
        await openLocalSession();
        if (!active) return;
        totalsStarted = true;
        void loadTotals();
        const filters = new URLSearchParams();
        for (const key of ["q", "account", "status", "date_from", "date_to"] as const)
          if (query[key]) filters.set(key, query[key]);
        void loadStats(filters);
        const params = new URLSearchParams(filters);
        params.set("page", String(query.page));
        params.set("page_size", String(query.pageSize));
        const response = await listInvoices(params);
        if (!active) return;
        setData(response);
        setLoading(false);
        if (!response.rows.length) return;
        try {
          const summaries = await getMatchingSummaries(response.rows.map((row) => row.id));
          if (active) setMatching(Object.fromEntries(summaries.rows.map((row) => [row.invoiceId, row])));
        } catch (reason) {
          if (active) setMatchingError(reason instanceof Error ? reason.message : "比对状态读取失败");
        }
      } catch (reason) {
        if (active) {
          const message = reason instanceof Error ? reason.message : "读取发票失败";
          setError(message);
          if (!totalsStarted) {
            setTotalsError(message);
            setTotalsLoading(false);
          }
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [query]);

  useEffect(() => {
    let active = true;
    if (selected) {
      getInvoice(selected).then(
        (value) => active && setDetail(value),
        (reason: unknown) =>
          active && setDetailError(reason instanceof Error ? reason.message : "读取明细失败"),
      );
    }
    return () => {
      active = false;
    };
  }, [selected]);

  const openMatching = (id: string) => navigate(matchingInvoicePath(id));
  return (
    <div className="invoice-list">
      <InvoiceSummary data={totals} loading={totalsLoading} error={totalsError} />
      <InvoiceCharts
        data={stats}
        loading={!stats && !statsError}
        error={statsError}
        accounts={accounts.items}
      />
      <Card className="invoice-list__panel" aria-labelledby="invoice-list-title">
        <CardHeader
          title={<span id="invoice-list-title">发票列表</span>}
          description={data ? `共 ${data.total} 张` : undefined}
        />
        <InvoiceFilters
          draft={draft}
          applied={query}
          accounts={accounts}
          loading={loading}
          onChange={setDraft}
          onSubmit={() =>
            changeQuery({ ...draft, page: 1, pageSize: query.pageSize, version: query.version + 1 })
          }
          onReset={() => {
            setDraft(emptyFilters);
            changeQuery({ ...emptyFilters, page: 1, pageSize: query.pageSize, version: query.version + 1 });
          }}
          onRefresh={() => changeQuery({ ...query, version: query.version + 1 })}
        />
        <InvoiceDetailRefresh state={detailRefresh} />
        {error && <Alert tone="danger">{error}，可点击“刷新数据”重试。</Alert>}
        {matchingError && <Alert tone="danger">{matchingError}，请点击“刷新数据”重试。</Alert>}
        {totalsError && totalsError !== error && (
          <Alert tone="danger">{totalsError}，请点击“刷新数据”重试。</Alert>
        )}
        {loading && <Skeleton label="正在读取数据库发票" rows={2} />}
        {data && !loading && (
          <>
            {data.rows.length === 0 ? (
              <EmptyState
                title="当前条件下没有发票"
                description="可调整筛选，或在“数据同步 → 柠檬云”导入发票。"
              />
            ) : (
              <InvoiceTable
                rows={data.rows}
                matching={matching}
                matchingError={matchingError}
                refresh={detailRefresh}
                onMatch={openMatching}
                onDetail={(id) => {
                  setDetail(null);
                  setDetailError("");
                  setSelected(id);
                }}
              />
            )}
            <CardFooter>
              <Pagination
                label="发票分页"
                total={data.total}
                page={data.page}
                pageCount={Math.max(1, Math.ceil(data.total / data.pageSize))}
                pageSize={data.pageSize}
                pageSizes={[10, 20, 50, 100]}
                disabled={loading}
                onPageChange={(page) => changeQuery({ ...query, page })}
                onPageSizeChange={(pageSize) => changeQuery({ ...query, page: 1, pageSize })}
              />
            </CardFooter>
          </>
        )}
      </Card>
      {selected && (
        <InvoiceDetailDrawer
          detail={detail}
          error={detailError}
          summary={matching[selected]}
          onClose={() => setSelected(null)}
          onMatch={openMatching}
        />
      )}
    </div>
  );
}
