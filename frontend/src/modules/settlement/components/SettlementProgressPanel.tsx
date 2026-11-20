import { useState } from "react";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardHeader,
  EmptyState,
  ErrorState,
  Skeleton,
} from "../../../shared/components/ui";
import { useSettlementProgress } from "../hooks/useSettlementProgress";
import { SettlementProgressChart } from "./SettlementProgressChart";

export function SettlementProgressPanel({
  consignee,
  currency,
  revision,
}: {
  consignee: string;
  currency: string;
  revision: number;
}) {
  const [retry, setRetry] = useState(0);
  const state = useSettlementProgress(consignee, currency, `${revision}:${retry}`);
  if (state.kind !== "ready")
    return (
      <Card>
        <CardHeader title="结汇进度" />
        <CardContent>
          {state.kind === "loading" ? (
            <Skeleton rows={4} label="正在读取结汇阶段金额" />
          ) : (
            <ErrorState
              title="结汇进度读取失败"
              message={state.message}
              action={<Button onClick={() => setRetry((value) => value + 1)}>重试</Button>}
            />
          )}
        </CardContent>
      </Card>
    );
  return (
    <>
      {state.result.currencies.length ? (
        state.result.currencies.map((data) => (
          <SettlementProgressChart key={data.currency} data={data} consignee={consignee} />
        ))
      ) : (
        <Card>
          <CardHeader title="结汇进度" />
          <CardContent>
            <EmptyState title="没有可统计的报关单" description="请调整筛选条件，或核对已导入的海关回执。" />
          </CardContent>
        </Card>
      )}
      {state.result.excludedCount > 0 && (
        <Alert tone="warning">
          {state.result.excludedCount} 张报关单因金额、币种或来源资料异常，未计入阶段金额图。
        </Alert>
      )}
    </>
  );
}
