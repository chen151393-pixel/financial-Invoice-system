import { Link } from "react-router";
import { settlementStagePath } from "../../../app/paths";
import { Badge, Card, CardContent, CardHeader, Progress } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { ProgressCurrency } from "../types/progress";
import "./settlement-progress.css";

/** 金额与几何宽度均由后端给出；同币种两条路径使用同一比较刻度。 */
export function SettlementProgressChart({ data, consignee }: { data: ProgressCurrency; consignee: string }) {
  return (
    <Card className="settlement-progress" aria-label={`${data.currency} 结汇进度`}>
      <CardHeader
        title="结汇进度"
        description="按回款路径查看各阶段的报关金额，点击阶段查看对应报关单。"
        actions={<Badge tone="neutral">{data.currency} · 按报关金额</Badge>}
      />
      <CardContent>
        <div className="settlement-progress__completion">
          <div>
            <span>已结汇报关金额</span>
            <strong>
              {money(data.settledAmount)} <small>{data.currency}</small>
            </strong>
            <span>
              {data.settledCount} / {data.count} 票已结汇
            </span>
          </div>
          <div className="settlement-progress__overall">
            <div>
              <strong>{data.settledPercentText}</strong>
              <span>
                报关总额 {money(data.amount)} · 未结汇 {money(data.unsettledAmount)}
              </span>
            </div>
            <Progress
              width={data.settledPercent}
              label="已结汇报关金额占比"
              text={data.settledPercentText}
              tone="success"
            />
          </div>
        </div>
        <div className="settlement-progress__routes">
          {data.routes.map((route) => (
            <section
              key={route.route}
              className="settlement-progress__route"
              aria-label={`${route.label}阶段金额`}
            >
              <header>
                <div>
                  <h4>{route.label}</h4>
                  <p>{route.note}</p>
                </div>
                <div>
                  <strong>{money(route.amount)}</strong>
                  <small>
                    {route.count} 票 · {data.currency}
                  </small>
                </div>
              </header>
              <ol className="settlement-progress__stages">
                {route.stages.map((stage) => {
                  const content = (
                    <>
                      <div className="settlement-progress__stage-title">
                        <span>{stage.label}</span>
                        <span>
                          <strong>{money(stage.amount)}</strong>
                          <small>{stage.count} 票</small>
                        </span>
                      </div>
                      <Progress
                        width={stage.barWidth}
                        label={`${stage.label}报关金额相对共同刻度`}
                        text={`${data.currency} ${money(stage.amount)}`}
                        tone={stage.tone}
                      />
                      <span className="settlement-progress__stage-note">{stage.note}</span>
                    </>
                  );
                  return (
                    <li key={stage.key}>
                      {stage.select.allowed ? (
                        <Link
                          className="settlement-progress__stage"
                          to={settlementStagePath({
                            route: route.route,
                            stage: stage.key,
                            currency: data.currency,
                            consignee,
                          })}
                          aria-label={`查看${route.label}${stage.label}：${data.currency} ${money(stage.amount)}，${stage.count}票`}
                        >
                          {content}
                        </Link>
                      ) : (
                        <div className="settlement-progress__stage" aria-disabled="true">
                          {content}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ol>
            </section>
          ))}
        </div>
        <p className="settlement-progress__caption">
          同币种共用刻度，条形满格为 {data.currency} {money(data.barMaximum)}
          。每张报关单仅计入一个阶段；阶段报关金额不等于未收金额。
        </p>
      </CardContent>
    </Card>
  );
}
