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
import { money } from "./format";
import type { InvoiceAccountOption, InvoiceStats } from "../types/invoice";

type Props = {
  data: InvoiceStats | null;
  loading: boolean;
  error: string;
  accounts: InvoiceAccountOption[];
};

/**
 * 进项发票分布：按月人民币价税合计、票面状态、柠檬云账套金额。金额与张数全部来自后端，口径与列表筛选一致；
 * 图上柱高与条长只用金额画图，显示的文字为后端十进制字符串。
 */
export function InvoiceCharts({ data, loading, error, accounts }: Props) {
  // 账套条形只按最大张数画长度，不作为业务百分比展示
  const widest = data ? Math.max(1, ...data.accounts.map((item) => Number(item.gross))) : 1;
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
        <CardHeader
          title="按月开票金额"
          description={
            data && data.otherCurrencyCount > 0
              ? `人民币价税合计，最近 6 个月；另有 ${data.otherCurrencyCount} 张非人民币发票未计入`
              : "人民币价税合计，最近 6 个月，按开票日期"
          }
        />
        <CardContent>
          {body((stats) => (
            <TrendChart
              label="按月开票金额"
              height={200}
              categories={stats.months.map((item) => `${Number(item.month.slice(5))}月`)}
              bars={[
                {
                  key: "gross",
                  label: "价税合计（元）",
                  values: stats.months.map((item) => Number(item.gross)),
                  texts: stats.months.map((item) => `¥ ${money(item.gross)} · ${item.count} 张`),
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
        <CardHeader title="柠檬云账套分布" description="按公司账套统计的人民币价税合计与张数" />
        <CardContent>
          {body((stats) =>
            stats.accounts.length === 0 ? (
              <EmptyState title="当前筛选无发票" />
            ) : (
              <ul className="invoice-charts__accounts">
                {stats.accounts.map((item) => (
                  <li key={item.account}>
                    <span>{accountLabel(item.account)}</span>
                    <strong>¥ {money(item.gross)}</strong>
                    <Progress
                      width={Math.max(0, Math.round((Number(item.gross) / widest) * 100))}
                      label={`${accountLabel(item.account)} 人民币价税合计`}
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
