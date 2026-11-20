import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  Skeleton,
} from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { HkRegistrationCheck } from "../types/hk-receipt";
export function HkReceiptReconciliation({
  data,
  loading,
  error,
  busy,
  formId,
  onCancel,
}: {
  data: HkRegistrationCheck | null;
  loading: boolean;
  error: string;
  busy: boolean;
  formId: string;
  onCancel: () => void;
}) {
  return (
    <aside className="hk-receipt__reconciliation">
      <Card>
        <CardHeader title="核对" />
        <CardContent aria-busy={loading}>
          {loading && !data ? (
            <Skeleton rows={5} label="正在核对香港到账" />
          ) : (
            data && (
              <>
                <dl className="hk-receipt__calculation">
                  <div>
                    <dt>到账金额 {data.currency}</dt>
                    <dd>{money(data.amount)}</dd>
                  </div>
                  <div>
                    <dt>+ 手续费</dt>
                    <dd>{money(data.fee)}</dd>
                  </div>
                  <div>
                    <dt>= 应对报关</dt>
                    <dd>{money(data.arrivedTotal)}</dd>
                  </div>
                  <div>
                    <dt>已选报关合计（{data.rows.length} 张）</dt>
                    <dd>{data.declaredTotal ? money(data.declaredTotal) : "—"}</dd>
                  </div>
                </dl>
                <div className="hk-receipt__difference" data-balanced={data.balanced}>
                  <strong>差额</strong>
                  <strong>{data.difference ? money(data.difference) : "—"}</strong>
                </div>
                <ul className="hk-receipt__checks">
                  {data.checks.map((check) => (
                    <li key={check.key}>
                      <Badge
                        tone={
                          check.state === "success"
                            ? "success"
                            : check.state === "warning"
                              ? "warning"
                              : "neutral"
                        }
                      >
                        {check.state === "success" ? "通过" : check.state === "warning" ? "提醒" : "待处理"}
                      </Badge>
                      <div>
                        <strong>{check.label}</strong>
                        <p>{check.detail}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              </>
            )
          )}
          {loading && (
            <p className="hk-receipt__hint" aria-live="polite">
              正在核对当前输入，核对完成后可提交。
            </p>
          )}
          {error && (
            <Alert tone="danger" title="核对未完成">
              {error}
            </Alert>
          )}
        </CardContent>
        <CardFooter>
          <div className="hk-receipt__submit">
            <Button
              type="submit"
              form={formId}
              variant="primary"
              disabled={busy || loading || !data?.submit.allowed || !!error}
            >
              {busy ? "正在登记…" : "登记并建批次"}
            </Button>
            {!loading && data && !data.submit.allowed && (
              <p className="hk-receipt__hint">{data.submit.reason}</p>
            )}
            <p className="hk-receipt__hint">
              提交后生成批次号。这批报关单的提单、销售合同和报关原件在批次中办理。
            </p>
            <Button type="button" variant="ghost" disabled={busy} onClick={onCancel}>
              取消，返回批次
            </Button>
          </div>
        </CardFooter>
      </Card>
    </aside>
  );
}
