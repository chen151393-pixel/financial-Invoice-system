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
import { nsPhaseOptions, statusTone, type NsBatch } from "../types/ns-plan";

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
  {
    key: "range",
    header: "创建日期范围",
    render: (row) => (row.startDate && row.endDate ? `${row.startDate} 至 ${row.endDate}` : "未限定日期"),
  },
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
    render: (row) => <Link to={syncNsBatchPath(row.requestId, row.recordType)}>查看执行明细</Link>,
  },
];

/** 总览和 NS 同步页共用同一执行记录视图，数量与分页来自后端。 */
export function NsPlanBatches() {
  const state = useNsPlanBatches();
  return <NsBatchRecords state={state} />;
}

export function NsBatchRecords({ state }: { state: ReturnType<typeof useNsPlanBatches> }) {
  const { data, error, refresh, change, phase } = state;
  return (
    <section className="sync-background sync-background--flush" aria-label="NS 同步执行记录">
      <div className="sync-background__head">
        <div className="sync-background__title">
          <h2>NS 同步执行记录</h2>
          <small>手动补拉与定时计划 · 北京时间</small>
        </div>
        <div className="sync-background__inline">
          <label>
            任务状态
            <select value={phase} onChange={(event) => change(1, event.target.value)}>
              {nsPhaseOptions.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <Button onClick={refresh}>刷新记录</Button>
        </div>
      </div>
      <div className="sync-background__body">
        {data && (
          <div className="sync-background__inline">
            {nsPhaseOptions
              .filter(([value]) => value && value !== "queued")
              .map(([value, label]) => (
                <Badge key={value} tone={statusTone(value)}>
                  {label} {data.counts[value] ?? 0}
                </Badge>
              ))}
          </div>
        )}
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
            title="当前条件下没有 NS 执行记录"
            description="手动补拉保存或定时计划执行后，记录会在这里显示。"
          />
        )}
        {data && data.items.length > 0 && (
          <>
            <DataTable
              label="NS 同步执行记录表"
              columns={columns}
              rows={data.items}
              rowKey={(row) => `${row.recordType}:${row.requestId}`}
              minWidth={860}
            />
            <Pagination
              label="NS 同步记录分页"
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
        <small>
          手动补拉每次分页保存记一条，显示当前登录身份在当前账套的记录；定时计划按批次汇总。新增 /
          更新包含关联补齐的单据。
        </small>
      </div>
    </section>
  );
}
