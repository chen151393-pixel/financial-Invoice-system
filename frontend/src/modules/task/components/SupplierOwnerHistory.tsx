import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  CardContent,
  DataTable,
  Dialog,
  EmptyState,
  ErrorState,
  Skeleton,
} from "../../../shared/components/ui";
import { getOwnerHistory } from "../api/supplier-owner";
import type { OwnerItem, OwnerVersion } from "../types/supplier-owner";

export function SupplierOwnerHistory({ item, onClose }: { item: OwnerItem; onClose: () => void }) {
  const [state, setState] = useState<
    { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; items: OwnerVersion[] }
  >({ kind: "loading" });
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    void getOwnerHistory(item.supplierId, item.companyId, controller.signal)
      .then((result) => {
        if (active) setState({ kind: "ready", items: result.items });
      })
      .catch((e: unknown) => {
        if (active) setState({ kind: "error", message: e instanceof Error ? e.message : "历史读取失败" });
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [item.supplierId, item.companyId, retry]);
  return (
    <Dialog title="人员关联变更历史" onClose={onClose} className="supplier-owner-history">
      <CardContent>
        <p>
          {item.supplierName} / {item.companyName}
        </p>
        <Alert>
          按保存版本保留全部记录；生效日期相同时采用较新版本。任务已保存的归属不因补录关系而自动改写。
        </Alert>
        {state.kind === "loading" ? (
          <Skeleton label="正在读取变更历史" />
        ) : state.kind === "error" ? (
          <ErrorState
            title="历史暂时无法加载"
            message={state.message}
            action={
              <Button
                onClick={() => {
                  setState({ kind: "loading" });
                  setRetry((v) => v + 1);
                }}
              >
                重新加载
              </Button>
            }
          />
        ) : state.items.length ? (
          <DataTable
            label="人员关联变更历史"
            rows={state.items}
            rowKey={(r) => r.id}
            minWidth={780}
            columns={[
              { key: "revision", header: "版本", render: (r) => r.revision },
              { key: "member", header: "负责人", render: (r) => r.memberName },
              { key: "date", header: "生效日期", render: (r) => r.effectiveDate },
              {
                key: "created",
                header: "保存时间",
                render: (r) => new Date(r.createdAt).toLocaleString("zh-CN"),
              },
              { key: "actor", header: "操作者", render: (r) => r.actor },
              { key: "reason", header: "调整原因", render: (r) => r.reason || "—" },
            ]}
          />
        ) : (
          <EmptyState title="尚无人员关联记录" description="新增关联后将在这里保留历次人员调整。" />
        )}
      </CardContent>
    </Dialog>
  );
}
