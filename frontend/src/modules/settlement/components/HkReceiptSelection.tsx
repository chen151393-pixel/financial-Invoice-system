import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  EmptyState,
  Skeleton,
} from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { HkRegistrationCheck } from "../types/hk-receipt";
export function HkReceiptSelection({
  numbers,
  data,
  loading,
  busy,
  onRemove,
  onReselect,
}: {
  numbers: string[];
  data: HkRegistrationCheck | null;
  loading: boolean;
  busy: boolean;
  onRemove: (number: string) => void;
  onReselect: () => void;
}) {
  return (
    <Card>
      <CardHeader
        title={`1 · 已选报关单（${numbers.length} 票）`}
        description="一条香港到账流水对应这些报关单；可在这里移除或返回补选。"
        actions={
          <Button variant="ghost" size="sm" type="button" disabled={busy} onClick={onReselect}>
            返回补选
          </Button>
        }
      />
      <CardContent>
        {numbers.length === 0 ? (
          <EmptyState title="还没有选择报关单" description="返回香港中转，勾选需要登记同一笔回款的报关单。" />
        ) : !data ? (
          <Skeleton rows={3} label="正在核对已选报关单" />
        ) : (
          <ul className="hk-receipt__selected">
            {data.rows
              .filter((row) => numbers.includes(row.declarationNo))
              .map((row) => (
                <li key={row.declarationNo}>
                  <div>
                    <strong>{row.declarationNo}</strong>{" "}
                    <Badge tone={row.select.allowed ? "neutral" : "warning"}>
                      {row.select.allowed ? "资料建批次后办理" : "当前不可登记"}
                    </Badge>
                    <p>
                      {row.consignee || row.select.reason} · 出口 {row.exportDate || "待核对"} ·{" "}
                      {row.waitingLabel} · {row.exportCompany || "出口抬头待核对"}
                    </p>
                  </div>
                  <strong>
                    {row.currency} {row.amount ? money(row.amount) : "—"}
                  </strong>
                  <Button size="sm" type="button" disabled={busy} onClick={() => onRemove(row.declarationNo)}>
                    移除
                  </Button>
                </li>
              ))}
          </ul>
        )}
        <div className="hk-receipt__selection-total">
          <span>报关合计</span>
          <strong>
            {loading
              ? "核对中…"
              : data?.declaredTotal
                ? `${data.currency} ${money(data.declaredTotal)}`
                : "—"}
          </strong>
        </div>
      </CardContent>
    </Card>
  );
}
