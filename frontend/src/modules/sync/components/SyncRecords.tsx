import { Link } from "react-router";
import { syncBatchPath, syncNsBatchPath } from "../../../app/paths";
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
import type { useSyncRecords } from "../hooks/useSyncRecords";
import { phaseOptions, syncTime } from "../types/background";
import { sourceOptions, type SyncRecord, type SyncSource } from "../types/history";
import { statusTone } from "../types/ns-plan";

const detailPath = (row: SyncRecord) =>
  row.source === "lemon" ? syncBatchPath(row.requestId) : syncNsBatchPath(row.requestId, row.recordType);

const columns: Column<SyncRecord>[] = [
  {
    key: "createdAt",
    header: "执行时间",
    render: (row) => (
      <>
        {syncTime(row.createdAt)}
        <small>{row.trigger === "schedule" ? "定时计划" : "手动提交"}</small>
      </>
    ),
  },
  {
    key: "source",
    header: "来源 / 类型",
    render: (row) => (
      <>
        {row.sourceLabel}
        <small>{row.kindLabel}</small>
      </>
    ),
  },
  {
    key: "range",
    header: "日期范围",
    render: (row) => (
      <>
        {row.startDate && row.endDate ? `${row.startDate} 至 ${row.endDate}` : "未限定日期"}
        <small>
          {row.rangeLabel}
          {row.source === "lemon" && row.businessTypes.length > 0 ? ` · ${row.businessTypes.join("、")}` : ""}
        </small>
      </>
    ),
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
  { key: "failed", header: "失败", align: "right", render: (row) => row.failed },
  {
    key: "action",
    header: "操作",
    render: (row) => (
      <Link to={detailPath(row)}>{row.source === "lemon" ? "查看账套明细" : "查看执行明细"}</Link>
    ),
  },
];

/** 同步中心的合并执行记录：NS 与柠檬云发票按执行时间倒序，数量与分页来自后端。 */
export function SyncRecords({ state }: { state: ReturnType<typeof useSyncRecords> }) {
  const { data, error, refresh, change, phase, source } = state;
  return (
    <section className="sync-background sync-background--flush" aria-label="同步执行记录">
      <div className="sync-background__head" id="sync-platforms">
        <div className="sync-background__title">
          <h2>同步执行记录</h2>
          <small>NS 与柠檬云发票 · 按执行时间倒序 · 北京时间</small>
        </div>
        <div className="sync-background__inline">
          <label>
            来源
            <select value={source} onChange={(event) => change({ source: event.target.value as SyncSource })}>
              {sourceOptions.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            任务状态
            <select value={phase} onChange={(event) => change({ phase: event.target.value })}>
              {phaseOptions.map(([value, label]) => (
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
            {phaseOptions
              .filter(([value]) => value && (data.counts[value] ?? 0) > 0)
              .map(([value, label]) => (
                <Badge key={value} tone={statusTone(value)}>
                  {label} {data.counts[value]}
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
            title="当前条件下没有执行记录"
            description="NS 手动补拉、定时计划或柠檬云后台拉取执行后，记录会在这里显示。"
          />
        )}
        {data && data.items.length > 0 && (
          <>
            <DataTable
              label="同步执行记录表"
              columns={columns}
              rows={data.items}
              rowKey={(row) => `${row.source}:${row.recordType}:${row.requestId}`}
              minWidth={960}
            />
            <Pagination
              label="同步执行记录分页"
              total={data.total}
              unit="条"
              page={data.page}
              pageCount={data.pages}
              pageSize={data.pageSize}
              pageSizes={[20]}
              onPageChange={(page) => change({ page })}
              onPageSizeChange={() => {}}
            />
          </>
        )}
        <small>
          NS 手动补拉每次分页保存记一条，只显示当前登录身份的记录；定时计划与柠檬云按批次汇总。NS 的新增 /
          更新包含关联补齐的单据。
        </small>
      </div>
    </section>
  );
}
