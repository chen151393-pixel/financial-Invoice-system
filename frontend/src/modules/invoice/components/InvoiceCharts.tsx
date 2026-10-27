import type { ReactNode } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  DonutChart,
  EmptyState,
  ErrorState,
  Progress,
  Skeleton,
  TrendChart,
} from "../../../shared/components/ui";
import type { InvoiceAccountOption, InvoiceStats } from "../types/invoice";

type Props = {
  data: InvoiceStats | null;
  loading: boolean;
  error: string;
  accounts: InvoiceAccountOption[];
};

/** 进项发票分布：按月张数、票面状态、柠檬云账套。计数全部来自后端，口径与列表筛选一致。 */
export function InvoiceCharts({ data, loading, error, accounts }: Props) {
  // 账套条形只按最大张数画长度，不作为业务百分比展示
  const widest = data ? Math.max(1, ...data.accounts.map((item) => item.count)) : 1;
  const accountLabel = (value: string) => accounts.find((item) => item.value === value)?.label ?? value;
  const body = (content: (stats: InvoiceStats) => ReactNode) =>
    loading ? (
      <Skeleton rows={3} label="正在统计" />
    ) : error ? (
      <ErrorState title="统计暂时无法读取" message={error} />
    ) : data ? (
      content(data)
    ) : null;
  return (
    <section className="invoice-charts" aria-label="发票分布">
      <Card>
        <CardHeader title="按月开票张数" description="最近 6 个月，按开票日期" />
        <CardContent>
          {body((stats) => (
            <TrendChart
              label="按月开票张数"
              height={200}
              categories={stats.months.map((item) => `${Number(item.month.slice(5))}月`)}
              bars={[
                {
                  key: "count",
                  label: "开票张数",
                  values: stats.months.map((item) => item.count),
                  texts: stats.months.map((item) => `${item.count} 张`),
                },
              ]}
            />
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader title="票面状态" description="红字与作废发票不参与比对" />
        <CardContent>
          {body((stats) =>
            stats.total === 0 ? (
              <EmptyState title="当前筛选无发票" />
            ) : (
              <DonutChart
                label="票面状态分布"
                centerLabel="张发票"
                centerValue={String(stats.total)}
                segments={stats.statuses
                  .filter((item) => item.count > 0)
                  .map((item) => ({
                    key: item.key,
                    label: item.label,
                    value: item.count,
                    text: `${item.count}`,
                  }))}
              />
            ),
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader title="柠檬云账套分布" description="按公司账套统计的发票张数" />
        <CardContent>
          {body((stats) =>
            stats.accounts.length === 0 ? (
              <EmptyState title="当前筛选无发票" />
            ) : (
              <ul className="invoice-charts__accounts">
                {stats.accounts.map((item) => (
                  <li key={item.account}>
                    <span>{accountLabel(item.account)}</span>
                    <strong>{item.count} 张</strong>
                    <Progress
                      width={Math.round((item.count / widest) * 100)}
                      label={`${accountLabel(item.account)} 发票张数`}
                      text={`${item.count} 张`}
                    />
                  </li>
                ))}
              </ul>
            ),
          )}
        </CardContent>
      </Card>
    </section>
  );
}
