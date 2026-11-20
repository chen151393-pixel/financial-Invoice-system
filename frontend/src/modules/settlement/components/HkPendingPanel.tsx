import { DeclarationDetailLink } from "./DeclarationDetailLink";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  DataTable,
  EmptyState,
  Pagination,
  type Column,
} from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { HkPending } from "../types/hk-workbench";
export function HkPendingPanel({
  rows,
  total,
  page,
  pageCount,
  pageSize,
  onPageSizeChange,
  selected,
  onToggle,
  onToggleAll,
  onPageChange,
  onRegister,
}: {
  rows: HkPending[];
  total: number;
  page: number;
  pageCount: number;
  pageSize: number;
  onPageSizeChange: (size: number) => void;
  selected: string[];
  onToggle: (row: HkPending) => void;
  onToggleAll: () => void;
  onPageChange: (page: number) => void;
  onRegister: () => void;
}) {
  const available = rows.filter((row) => row.select.allowed);
  const columns: Column<HkPending>[] = [
    {
      key: "select",
      header: (
        <input
          type="checkbox"
          aria-label="选择本页可登记报关单"
          checked={available.length > 0 && available.every((row) => selected.includes(row.declarationNo))}
          disabled={!available.length}
          onChange={onToggleAll}
        />
      ),
      width: "46px",
      render: (row) => (
        <input
          type="checkbox"
          aria-label={`选择报关单 ${row.declarationNo}`}
          checked={selected.includes(row.declarationNo)}
          disabled={!row.select.allowed}
          title={row.select.reason}
          onChange={() => onToggle(row)}
        />
      ),
    },
    {
      key: "declaration",
      header: "待登记报关单",
      render: (row) => (
        <div className="settlement-cell">
          <strong>
            <DeclarationDetailLink number={row.declarationNo} />
          </strong>
          <span>
            {row.recordNo} · 出口 {row.exportDate || "待补"}
          </span>
        </div>
      ),
    },
    {
      key: "customer",
      header: "境外收货人 / 出口抬头",
      render: (row) => (
        <div className="settlement-cell">
          <span>{row.consignee}</span>
          <small>{row.exportCompany || "出口抬头待补"}</small>
        </div>
      ),
    },
    {
      key: "amount",
      header: "报关金额",
      align: "right",
      render: (row) => (
        <strong>
          {row.currency} {row.amount ? money(row.amount) : "—"}
        </strong>
      ),
    },
    {
      key: "waiting",
      header: "等待 / 状态",
      render: (row) => (
        <div className="settlement-cell">
          <span>{row.waitingLabel}</span>
          <Badge tone="warning">{row.select.reason || "待登记回款"}</Badge>
        </div>
      ),
    },
  ];
  return (
    <Card className="settlement-hk-pending">
      <CardHeader
        title="待登记回款的报关单"
        description="勾选同一境外收货人、同一币种的报关单，登记一条香港到账流水并生成批次。"
        actions={
          <Button variant="primary" disabled={!selected.length} onClick={onRegister}>
            登记回款{selected.length ? `（${selected.length} 票）` : ""}
          </Button>
        }
      />
      <CardContent flush>
        {rows.length ? (
          <DataTable
            label="待登记香港回款报关单"
            columns={columns}
            rows={rows}
            rowKey={(row) => row.declarationNo}
            minWidth={800}
            density="compact"
          />
        ) : (
          <EmptyState
            title="没有待登记回款的报关单"
            description="海关回执匹配且未被有效批次占用的香港中转报关单会显示在这里。"
          />
        )}
      </CardContent>
      {total > 0 && (
        <CardFooter>
          <span className="settlement-hk-selection">
            {selected.length
              ? `已选 ${selected.length} 票，登记为同一条香港到账流水`
              : "尚无批次，登记回款后办理提单和销售合同"}
          </span>
          <Pagination
            label="待登记报关单分页"
            total={total}
            unit="票"
            page={page}
            pageCount={pageCount}
            pageSize={pageSize}
            pageSizes={[20, 50, 100]}
            onPageSizeChange={onPageSizeChange}
            onPageChange={onPageChange}
          />
        </CardFooter>
      )}
    </Card>
  );
}
