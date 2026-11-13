import { useEffect, useId, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  Field,
} from "../../../shared/components/ui";
import { useOwnerChange } from "../hooks/useOwnerChange";
import type { OwnerItem, OwnerOptions } from "../types/supplier-owner";

export function SupplierOwnerEditor({
  items,
  options,
  onClose,
  onSaved,
  onBusy,
}: {
  items: OwnerItem[];
  options: OwnerOptions;
  onClose: () => void;
  onSaved: (message: string) => void;
  onBusy: (busy: boolean) => void;
}) {
  const [supplierId, setSupplierId] = useState(items[0]?.supplierId.toString() || "");
  const [companyId, setCompanyId] = useState(items[0]?.companyId.toString() || "");
  const [memberId, setMemberId] = useState(items.length === 1 ? items[0].current?.memberId || "" : "");
  const [date, setDate] = useState(options.today);
  const [reason, setReason] = useState("");
  const [transfer, setTransfer] = useState(false);
  const { preview, error, busy, invalidate, inspect, save } = useOwnerChange(onSaved);
  const firstInput = useRef<HTMLSelectElement>(null);
  const helpId = useId();
  useEffect(() => {
    firstInput.current?.focus();
  }, []);
  useEffect(() => {
    onBusy(busy);
    return () => onBusy(false);
  }, [busy, onBusy]);
  const title = items.length > 1 ? "批量更换负责人" : items.length ? "维护人员关联" : "新增人员关联";
  return (
    <Card className="supplier-owner-editor">
      <CardHeader
        title={title}
        description={items.length > 1 ? `已选择 ${items.length} 条供应商与采购抬头关系` : undefined}
      />
      <form
        className="supplier-owner-form"
        onChange={invalidate}
        onSubmit={(e) => {
          e.preventDefault();
          void inspect({
            items: items.length
              ? items.map(({ supplierId, companyId, revision }) => ({ supplierId, companyId, revision }))
              : [{ supplierId: Number(supplierId), companyId: Number(companyId), revision: 0 }],
            memberId: Number(memberId),
            effectiveDate: date,
            reason,
            transferOpenTasks: transfer,
          });
        }}
      >
        <CardContent>
          <fieldset disabled={busy}>
            {items.length === 0 ? (
              <>
                <Field label="供应商">
                  <select
                    ref={firstInput}
                    required
                    value={supplierId}
                    onChange={(e) => setSupplierId(e.target.value)}
                  >
                    <option value="">请选择供应商</option>
                    {options.suppliers.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.name}（{r.account}）
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="采购抬头">
                  <select required value={companyId} onChange={(e) => setCompanyId(e.target.value)}>
                    <option value="">请选择采购抬头</option>
                    {options.companies.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.name}（{r.account}）
                      </option>
                    ))}
                  </select>
                </Field>
              </>
            ) : items.length === 1 ? (
              <dl className="supplier-owner-context">
                <div>
                  <dt>供应商</dt>
                  <dd>{items[0].supplierName}</dd>
                </div>
                <div>
                  <dt>采购抬头</dt>
                  <dd>{items[0].companyName}</dd>
                </div>
              </dl>
            ) : (
              <details className="supplier-owner-scope">
                <summary>查看本次更换范围</summary>
                <ul>
                  {items.map((r) => (
                    <li key={`${r.supplierId}:${r.companyId}`}>
                      {r.supplierName} / {r.companyName}：{r.current?.memberName || "待分配"}
                    </li>
                  ))}
                </ul>
              </details>
            )}
            <Field label="负责人">
              <select
                ref={items.length ? firstInput : undefined}
                required
                value={memberId}
                aria-describedby={`${helpId}-member`}
                onChange={(e) => setMemberId(e.target.value)}
              >
                <option value="">请选择飞书成员</option>
                {options.members.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </select>
              <small id={`${helpId}-member`} className="supplier-owner-help">
                从已导入的飞书成员中选择。
              </small>
            </Field>
            <Field label="生效日期">
              <input required type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </Field>
            <Field label="备注">
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={300}
                rows={2}
                placeholder="填写人员分工或调整原因"
              />
            </Field>
            <div className="supplier-owner-transfer">
              <label className="supplier-owner-check">
                <input
                  type="checkbox"
                  checked={transfer}
                  aria-describedby={`${helpId}-transfer`}
                  onChange={(e) => setTransfer(e.target.checked)}
                />
                <span>同时交接这些关系下的未完成任务</span>
              </label>
              <p id={`${helpId}-transfer`} className="supplier-owner-help">
                未来日期用于新业务的计划归属；未完成任务在实际交接当日操作。
              </p>
            </div>
          </fieldset>
          <details className="supplier-owner-rules">
            <summary>历史归属保留</summary>
            <p>
              默认只影响生效后的新任务；更换人员不改写已完成任务的历史业绩。显式交接从本次保存时生效，交接前的归属仍保留。
            </p>
          </details>
          {error && (
            <div className="supplier-owner-feedback">
              <Alert tone="danger" title="变更未完成">
                {error}
              </Alert>
            </div>
          )}
          {preview && (
            <div className="supplier-owner-feedback" role="status">
              <Alert title="变更预览">
                <p>
                  {preview.pairCount} 条关系将于 {preview.effectiveDate} 起归属 {preview.memberName}。
                </p>
                <p>
                  涉及 {preview.openTaskCount} 个未完成任务；本次{transfer ? "一并交接" : "保留原任务归属"}。
                </p>
                <p>{preview.transferReason}</p>
              </Alert>
            </div>
          )}
        </CardContent>
        <CardFooter>
          <Button disabled={busy} onClick={onClose}>
            取消
          </Button>
          <Button type="submit" variant={preview ? "secondary" : "primary"} disabled={busy}>
            {busy ? "处理中…" : preview ? "重新预览" : "预览变更"}
          </Button>
          {preview && (
            <Button variant="primary" disabled={busy} onClick={() => void save()}>
              确认保存
            </Button>
          )}
        </CardFooter>
      </form>
    </Card>
  );
}
