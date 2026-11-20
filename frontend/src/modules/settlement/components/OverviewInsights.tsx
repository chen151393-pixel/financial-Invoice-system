import { Link } from "react-router";
import { settlementOverviewActionPath } from "../../../app/paths";
import { Badge, Card, CardContent, CardHeader, EmptyState, Progress } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { OverviewInsight } from "../types/overview";

/** 账龄是未结汇报关金额；待办的金额与范围均由后端提供。 */
export function OverviewInsights({ data, asOf }: { data: OverviewInsight; asOf: string }) {
  return (
    <div className="settlement-overview-insights">
      <Card aria-label={`${data.currency} 未结汇账龄`}>
        <CardHeader title="未结汇账龄" description={`按出口日期起算 · 未结汇报关金额 · ${data.currency}`} />
        <CardContent>
          <dl className="settlement-overview-aging">
            {data.aging.map((bucket) => (
              <div key={bucket.label}>
                <dt>{bucket.label}</dt>
                <dd>
                  <Progress
                    fluid
                    width={bucket.barWidth}
                    label={`${bucket.label}未结汇金额相对最大账龄段`}
                    tone={bucket.tone}
                  />
                </dd>
                <dd>
                  <strong>{money(bucket.amount)}</strong>
                  <small>{bucket.count} 票</small>
                </dd>
              </div>
            ))}
          </dl>
          <p className="settlement-overview-insight-note">
            合计未结汇 {money(data.unsettledAmount)} · {data.unsettledCount} 票
          </p>
          {data.unknownDateCount > 0 && (
            <p className="settlement-overview-insight-note">
              其中 {data.unknownDateCount} 票缺出口日期，已计入合计，未计入账龄分段。
            </p>
          )}
          <p className="settlement-overview-insight-note">统计截至 {asOf}</p>
        </CardContent>
      </Card>
      <Card aria-label={`${data.currency} 需要处理`}>
        <CardHeader title="需要处理" description="异常优先，其次是能推进的下一步" />
        <CardContent>
          {data.actions.length ? (
            <ul className="settlement-overview-actions">
              {data.actions.map((action) => (
                <li key={action.key}>
                  <Link
                    className="settlement-overview-action"
                    data-tone={action.tone}
                    to={settlementOverviewActionPath(action, data.currency)}
                  >
                    <span>
                      <Badge tone={action.tone}>{action.title}</Badge>
                      <small>{action.description}</small>
                    </span>
                    <strong>{money(action.amount)}</strong>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="暂无待处理事项" description="当前筛选范围内没有需要推进的收汇事项。" />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
