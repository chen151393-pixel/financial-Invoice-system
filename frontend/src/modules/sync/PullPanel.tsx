import { useState } from "react";
import { Button } from "../../shared/components/Button";
import type { DateRange, Source } from "./api";
import { PullProgress } from "./PullProgress";
import { PullResults } from "./PullResults";
import { useRangePull } from "./useRangePull";

export function PullPanel({
  source,
  onBusyChange,
}: {
  source: Source;
  onBusyChange: (busy: boolean) => void;
}) {
  const [range, setRange] = useState<DateRange>({ startDate: "", endDate: "" });
  const task = useRangePull(source.kind, onBusyChange);
  const result = task.pages[task.pageIndex];
  const changed =
    task.submittedRange !== null &&
    (range.startDate !== task.submittedRange.startDate || range.endDate !== task.submittedRange.endDate);
  return (
    <section
      className="sync-page__panel sync-page__results"
      aria-busy={task.busy}
      aria-label={`${source.label}拉取结果`}
    >
      <div className="sync-page__heading">
        <div>
          <div className="sync-page__result-title">
            <h2>{source.label}</h2>
            <span className="sync-page__tag">不修改 NS</span>
          </div>
          <p>{source.reason}</p>
        </div>
      </div>
      <form
        className="sync-page__filters"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          void task.start(range, false);
        }}
      >
        <fieldset disabled={task.busy}>
          <legend>按创建日期拉取</legend>
          <div className="sync-page__date-fields">
            <label htmlFor={`${source.kind}-start`}>
              开始日期（必填）
              <input
                id={`${source.kind}-start`}
                type="date"
                value={range.startDate}
                aria-required="true"
                aria-describedby={`${source.kind}-date-help`}
                onChange={(event) => setRange((value) => ({ ...value, startDate: event.target.value }))}
              />
            </label>
            <label htmlFor={`${source.kind}-end`}>
              结束日期（必填）
              <input
                id={`${source.kind}-end`}
                type="date"
                value={range.endDate}
                aria-required="true"
                aria-describedby={`${source.kind}-date-help`}
                onChange={(event) => setRange((value) => ({ ...value, endDate: event.target.value }))}
              />
            </label>
            <Button type="submit" disabled={!source.allowed || task.busy}>
              拉取时间段数据
            </Button>
            <Button
              variant="primary"
              disabled={!source.storageAllowed || task.busy}
              onClick={() => void task.start(range, true)}
            >
              拉取时间段并保存
            </Button>
            <Button
              disabled={task.busy || (!range.startDate && !range.endDate)}
              onClick={() => setRange({ startDate: "", endDate: "" })}
            >
              清空日期
            </Button>
          </div>
          <p id={`${source.kind}-date-help`}>
            按 NS 查询时区，包含起止当天。选择开始和结束日期后，自动分批拉取该时间段全部数据，每批最多 20 张。
          </p>
          <p>
            {source.storageReason}
            。按完整报关关联组分别保存，成功组立即提交，失败组单独列出；关联单据可能超出筛选日期，重复同步更新原记录。
          </p>
        </fieldset>
      </form>
      {changed && (
        <p className="sync-page__scope-change" role="status">
          日期条件已修改，下方仍为上次时间段的结果；请重新拉取。
        </p>
      )}
      {task.busy && (
        <div className="sync-page__feedback" role="status">
          <span className="sync-page__loader" aria-hidden="true" />
          {task.status === "stopping"
            ? "正在等待当前批次完成，随后停止"
            : `已完成 ${task.pages.length} 批，正在处理第 ${task.pages.length + 1} 批…`}
          <Button disabled={task.status === "stopping"} onClick={task.stop}>
            停止后续拉取
          </Button>
        </div>
      )}
      {task.busy && <PullProgress run={task.run} unavailable={task.progressUnavailable} />}
      {task.status === "completed" && (
        <p className="sync-page__result-summary" role="status">
          所选时间段拉取完成，共完成 {task.pages.length} 批。
          {result?.storage ? "各批单据均已保存，待核实提示请逐批查看。" : "仅展示数据，未保存到本地数据库。"}
        </p>
      )}
      {task.status === "partial" && (
        <p className="sync-page__scope-change" role="status">
          所选时间段已处理完，共 {task.pages.length} 批，存在失败单据。成功数据已保存，请逐批查看失败原因。
        </p>
      )}
      {task.status === "recovered" && (
        <p className="sync-page__scope-change" role="status">
          已恢复刷新前最后一批的保存结果，见下方逐单结果；该时间段后续批次未继续，如需继续请重新拉取。
        </p>
      )}
      {task.status === "stopped" && (
        <p className="sync-page__scope-change" role="status">
          已停止，完成 {task.pages.length} 批；所选时间段尚未拉取完。已提交的保存结果保留。
        </p>
      )}
      {task.error && (
        <p role="alert" className="sync-page__error">
          {task.error}。本次未完整完成，已完成 {task.pages.length} 批；已提交的数据保留。
          结果待核实时，请先在财务核对页核对本地记录，再决定是否重新拉取。
        </p>
      )}
      {!result && task.status === "idle" && (
        <div className="sync-page__empty">
          <strong>{source.allowed ? `准备读取${source.label}` : "当前单据暂不可拉取"}</strong>
          <p>{source.allowed ? "选择日期后，可拉取整个时间段查看，或拉取并保存到 MySQL。" : source.reason}</p>
          <span className="sync-page__empty-note">自动分批 · 不修改源单据</span>
        </div>
      )}
      {result && (
        <>
          <div className="sync-page__pagination">
            <span>
              查看已完成批次 {task.pageIndex + 1} / {task.pages.length}（以下计数仅属于本批）
            </span>
            <div>
              <Button
                disabled={task.busy || task.pageIndex === 0}
                onClick={() => task.setPageIndex(task.pageIndex - 1)}
              >
                上一批结果
              </Button>{" "}
              <Button
                disabled={task.busy || task.pageIndex + 1 >= task.pages.length}
                onClick={() => task.setPageIndex(task.pageIndex + 1)}
              >
                下一批结果
              </Button>
            </div>
          </div>
          <PullResults result={result} />
        </>
      )}
    </section>
  );
}
