import { Link } from "react-router";
import { syncNsBatchPath } from "../../../app/paths";
import {
  Badge,
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  Pagination,
  Skeleton,
  type Column,
} from "../../../shared/components/ui";
import { useNsPlanBatches } from "../hooks/useNsPlanBatches";
import { syncTime } from "../types/background";
import { statusTone, type NsBatch } from "../types/ns-plan";

const columns: Column<NsBatch>[] = [
  {
    key: "createdAt",
    header: "触发时间",
    render: (row) => (
      <>
        {syncTime(row.createdAt)}
        <small>{row.trigger === "schedule" ? "定时计划" : "手动提交"}</small>
      </>
    ),
  },
  { key: "kind", header: "单据类型", render: (row) => row.kindLabel },
  { key: "range", header: "创建日期范围", render: (row) => `${row.startDate} 至 ${row.endDate}` },
  {
    key: "phase",
    header: "状态",
    render: (row) => (
      <>
        <Badge tone={statusTone(row.phase)}>{row.label}</Badge>
        <small>{row.message}</small>
      </>
    ),
  },
  { key: "fetched", header: "读取", align: "right", render: (row) => row.fetched },
  { key: "saved", header: "新增 / 更新", align: "right", render: (row) => `${row.created} / ${row.updated}` },
  { key: "failed", header: "失败单据", align: "right", render: (row) => row.failed },
  {
    key: "action",
    header: "操作",
    render: (row) => <Link to={syncNsBatchPath(row.requestId)}>查看分页明细</Link>,
  },
];

/** NS 定时计划的执行记录：一行一个计划批次（每种单据类型各一批），统计来自后端已保存结果。 */
export function NsPlanBatches() {
  const { data, error, refresh, change } = useNsPlanBatches();
  return (
    <section className="sync-background sync-background--flush" aria-label="NS 计划执行记录">
      <div className="sync-background__head">
        <div className="sync-background__title">
          <h2>计划执行记录</h2>
          <small>北京时间 · 新增/更新含随报关补齐的子采购单</small>
        </div>
        <Button onClick={refresh}>刷新记录</Button>
      </div>
      <div className="sync-background__body">
        {error && data && (
          <p role="alert" className="sync-background__error">
            {error}；以下记录可能不是最新状态。
          </p>
        )}
        {!data &&
          (error ? (
            <ErrorState
              title="执行记录读取失败"
              message={error}
              action={<Button onClick={refresh}>重新读取</Button>}
            />
          ) : (
            <Skeleton label="正在读取执行记录" />
          ))}
        {data && data.items.length === 0 && (
          <EmptyState
            title="还没有计划执行记录"
            description="启用并保存定时计划后，到达执行时间会在这里出现批次。"
          />
        )}
        {data && data.items.length > 0 && (
          <>
            <DataTable
              label="NS 计划批次表"
              columns={columns}
              rows={data.items}
              rowKey={(row) => row.requestId}
              minWidth={860}
            />
            <Pagination
              label="计划批次分页"
              total={data.total}
              unit="批"
              page={data.page}
              pageCount={data.pages}
              pageSize={data.pageSize}
              pageSizes={[20]}
              onPageChange={change}
              onPageSizeChange={() => {}}
            />
          </>
        )}
      </div>
    </section>
  );
}
