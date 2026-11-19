import { useEffect, useState } from "react";
import { Link } from "react-router";
import { paths } from "../../../app/paths";
import {
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
import { queryBankReceipts } from "../api";
import { BankReceiptImportDialog } from "../components/BankReceiptImportDialog";
import { BankReceiptStats } from "../components/BankReceiptStats";
import type { BankReceipt, BankReceiptList, BankReceiptQuery, ThirdPartyFilter } from "../types";
import "../components/settlement.css";

type State =
  | { kind: "loading" }
  | { kind: "ready"; result: BankReceiptList }
  | { kind: "error"; message: string };

const INITIAL: BankReceiptQuery = {
  customer: "",
  receivingCompany: "",
  receiptFrom: null,
  receiptTo: null,
  thirdParty: "all",
  page: 1,
  pageSize: 20,
};

const COLUMNS: Column<BankReceipt>[] = [
  {
    key: "date",
    header: "收汇日期 / 流水号",
    render: (row) => (
      <div className="settlement-cell">
        {[row.receiptDate, row.receiptTime].filter(Boolean).join(" ")}
        {row.reference && <span>{row.reference}</span>}
      </div>
    ),
  },
  {
    key: "company",
    header: "收汇抬头（收款账户）",
    render: (row) => (
      <div className="settlement-cell">
        {row.receivingCompany}
        <span>{row.receivingAccount || "—"}</span>
      </div>
    ),
  },
  { key: "payer", header: "付款人户名", render: (row) => row.payerName },
  {
    key: "customer",
    header: "实际客户（境外收货人）",
    render: (row) => <strong>{row.customerName}</strong>,
  },
  {
    key: "amount",
    header: "收汇金额",
    align: "right",
    render: (row) => <strong>{`${row.currency} ${money(row.amount)}`}</strong>,
  },
  {
    key: "thirdParty",
    header: "三方代付",
    render: (row) => (row.thirdParty ? <Badge tone="progress">三方代付</Badge> : "—"),
  },
  {
    key: "route",
    header: "去向",
    render: (row) =>
      row.route === "direct" ? (
        <Link to={paths.settlementDirect}>直接收汇明细</Link>
      ) : (
        <div className="settlement-cell">
          <div>
            <Badge tone="info">{row.routeLabel}</Badge>
          </div>
          <span>不进总账，在批次登记汇回</span>
        </div>
      ),
  },
];

/** 银行收汇明细：境内美金账户收汇记录；实际客户取导入表格，三方代付只作标记。 */
export function SettlementBankReceiptsPage() {
  const [query, setQuery] = useState<BankReceiptQuery>(INITIAL);
  const [state, setState] = useState<State>({ kind: "loading" });
  const [refresh, setRefresh] = useState(0);
  const [importOpen, setImportOpen] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setState({ kind: "loading" });
      try {
        setState({ kind: "ready", result: await queryBankReceipts(query, controller.signal) });
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
      {state.kind === "ready" && state.result.totals.length > 0 && (
        <BankReceiptStats totals={state.result.totals} />
      )}
      <Card>
        <CardHeader
          title="收汇记录"
          description="收汇按表格中的实际客户归到境外收货人；付款人户名与实际客户不同的标为三方代付。"
          actions={
            <Button variant="primary" onClick={() => setImportOpen(true)}>
              导入银行流水
            </Button>
          }
        />
        <FilterBar
          embedded
          onSubmit={(form) => {
            const data = new FormData(form);
            setQuery({
              ...query,
              customer: String(data.get("customer") || "").trim(),
              receivingCompany: String(data.get("receivingCompany") || "").trim(),
              receiptFrom: String(data.get("receiptFrom") || "") || null,
              receiptTo: String(data.get("receiptTo") || "") || null,
              thirdParty: String(data.get("thirdParty") || "all") as ThirdPartyFilter,
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
          <Field label="实际客户（境外收货人）" grow>
            <input name="customer" placeholder="按表格中的名称搜索" />
          </Field>
          <Field label="收汇抬头" grow>
            <input name="receivingCompany" placeholder="如 上海毅鑫" />
          </Field>
          <Field label="收汇日期 从">
            <input type="date" name="receiptFrom" />
          </Field>
          <Field label="至">
            <input type="date" name="receiptTo" aria-label="收汇日期 至" />
          </Field>
          <Field label="三方代付">
            <select name="thirdParty" defaultValue={INITIAL.thirdParty}>
              <option value="all">全部</option>
              <option value="yes">仅三方代付</option>
              <option value="no">非三方代付</option>
            </select>
          </Field>
        </FilterBar>
        <CardContent flush>
          {state.kind === "loading" && <Skeleton rows={4} label="正在读取银行收汇明细" />}
          {state.kind === "error" && (
            <ErrorState
              title="银行收汇明细读取失败"
              message={state.message}
              action={<Button onClick={() => setRefresh((n) => n + 1)}>重试</Button>}
            />
          )}
          {state.kind === "ready" &&
            (state.result.items.length ? (
              <DataTable
                label="银行收汇记录"
                columns={COLUMNS}
                rows={state.result.items}
                rowKey={(row) => String(row.id)}
                minWidth={1040}
              />
            ) : (
              <EmptyState
                title="没有符合条件的收汇记录"
                description="银行流水表格导入后，收汇记录出现在这里。"
              />
            ))}
        </CardContent>
        {state.kind === "ready" && state.result.total > 0 && (
          <CardFooter>
            <Pagination
              label="银行收汇分页"
              total={state.result.total}
              unit="笔"
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
      {importOpen && (
        <BankReceiptImportDialog
          onClose={() => setImportOpen(false)}
          onImported={() => setQuery((current) => ({ ...current, page: 1 }))}
        />
      )}
    </div>
  );
}
