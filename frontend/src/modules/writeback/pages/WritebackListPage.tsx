import { useEffect, useState } from "react";
import { Link } from "react-router";
import { writebackRequestPath } from "../../../app/paths";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  EmptyState,
  ErrorState,
  Field,
  FilterBar,
  Pagination,
  Skeleton,
} from "../../../shared/components/ui";
import { listTasks } from "../api";
import type { TaskList } from "../types";
import "../writeback.css";

export function WritebackListPage() {
  const [query, setQuery] = useState({ keyword: "", state: "", page: 1, pageSize: 20 });
  const [data, setData] = useState<TaskList | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    listTasks(query)
      .then((result) => {
        if (active) {
          setData(result);
          setError("");
          setLoading(false);
        }
      })
      .catch((e: unknown) => {
        if (active) {
          setError(e instanceof Error ? e.message : "任务加载失败");
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [query, refresh]);
  function change(patch: Partial<typeof query>) {
    setLoading(true);
    setQuery({ ...query, ...patch });
  }
  return (
    <div className="wb-prepare">
      <Alert title="回写准备">
        整张发票完整审核后自动生成任务。当前可查询和确认账单方案，尚不执行 NS 写入。
      </Alert>
      <Card>
        <CardHeader
          title="回写任务"
          description="按发票保留审核快照；历史扫描任务须人工核实。"
          actions={
            <Button
              disabled={loading}
              onClick={() => {
                setLoading(true);
                setRefresh((n) => n + 1);
              }}
            >
              刷新列表
            </Button>
          }
        />
        <FilterBar
          embedded
          onSubmit={(form) => {
            const values = new FormData(form);
            change({
              keyword: String(values.get("keyword") || ""),
              state: String(values.get("state") || ""),
              page: 1,
            });
          }}
          actions={
            <Button type="submit" variant="primary" disabled={loading}>
              查询
            </Button>
          }
        >
          <Field label="任务、发票或供应商" grow>
            <input name="keyword" placeholder="输入任务号、发票号码或供应商" maxLength={100} />
          </Field>
          <Field label="状态">
            <select name="state">
              <option value="">全部状态</option>
              <option value="queued">待匹配账单</option>
              <option value="waiting_bill">等待账单</option>
              <option value="needs_confirmation">待确认账单</option>
              <option value="ready">方案已确认</option>
              <option value="blocked">待处理</option>
              <option value="stale">审核已失效</option>
            </select>
          </Field>
        </FilterBar>
        {loading ? (
          <Skeleton label="正在加载回写任务" />
        ) : error ? (
          <ErrorState title="任务加载失败" message={error} />
        ) : data?.items.length ? (
          <DataTable
            label="回写任务"
            rows={data.items}
            rowKey={(row) => row.id}
            columns={[
              {
                key: "invoice",
                header: "发票 / 任务",
                render: (row) => (
                  <>
                    <Link to={writebackRequestPath(row.id)}>{row.invoiceNo}</Link>
                    <small className="wb-secondary">{row.taskNo}</small>
                  </>
                ),
              },
              { key: "vendor", header: "供应商", render: (row) => row.vendorName },
              { key: "amount", header: "含税金额（元）", align: "right", render: (row) => row.amount },
              { key: "state", header: "状态", render: (row) => <Badge>{row.stateLabel}</Badge> },
              { key: "reason", header: "处理说明", render: (row) => row.reason },
            ]}
          />
        ) : (
          <EmptyState
            title="暂无回写任务"
            description="完成整票分配审核后自动生成任务；历史发票可在匹配详情重新检查。"
          />
        )}
        {data && (
          <Pagination
            label="回写任务分页"
            total={data.total}
            page={data.page}
            pageCount={data.pages}
            pageSize={data.pageSize}
            pageSizes={[20, 50, 100]}
            disabled={loading}
            onPageChange={(page) => change({ page })}
            onPageSizeChange={(pageSize) => change({ pageSize, page: 1 })}
          />
        )}
      </Card>
    </div>
  );
}
