import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  EmptyState,
  ErrorState,
  Progress,
  Skeleton,
} from "../../../shared/components/ui";
import { getInvoicingSpeed } from "../api/supplier-group";
import type { InvoicingSpeed } from "../types/supplier-group";

/** 开票时效：通知供应商到发票收齐的平均天数（后端统计），偏慢的供应商用橙色并标“偏慢”。 */
export function InvoicingSpeedCard() {
  const [data, setData] = useState<InvoicingSpeed | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    getInvoicingSpeed().then(
      (value) => active && setData(value),
      (reason: unknown) => active && setError(reason instanceof Error ? reason.message : "开票时效读取失败"),
    );
    return () => {
      active = false;
    };
  }, []);
  // 条长只按最慢的天数画图
  const longest = data ? Math.max(1, ...data.suppliers.map((item) => Number(item.days))) : 1;
  return (
    <Card className="sg-speed" aria-labelledby="sg-speed-title">
      <CardHeader
        title={<span id="sg-speed-title">开票时效</span>}
        description={
          data ? `通知到收齐发票的平均天数 · 近 ${data.windowDays} 天` : "通知到收齐发票的平均天数"
        }
      />
      <CardContent>
        {!data && !error && <Skeleton rows={3} label="正在统计开票时效" />}
        {error && <ErrorState title="开票时效暂时无法读取" message={error} />}
        {data &&
          (data.suppliers.length === 0 ? (
            <EmptyState title="暂无可统计的任务" description="通知后发票全部收齐的任务才计入。" />
          ) : (
            <>
              <ul className="sg-speed__list">
                {data.suppliers.map((item) => (
                  <li key={item.supplierId || item.supplier}>
                    <span>{item.supplier}</span>
                    <strong data-slow={item.slow}>
                      {item.days} 天{item.slow ? " · 偏慢" : ""}
                    </strong>
                    <Progress
                      width={Math.round((Number(item.days) / longest) * 100)}
                      tone={item.slow ? "warning" : "info"}
                      label={`${item.supplier} 平均开票天数`}
                      text={`${item.tasks} 个任务`}
                    />
                  </li>
                ))}
              </ul>
              <p className="sg-speed__note">
                平均 {data.average} 天（{data.taskCount} 个任务）· 超过 {data.slowDays}{" "}
                天标为偏慢，可在通知时提前催促
              </p>
            </>
          ))}
      </CardContent>
    </Card>
  );
}
