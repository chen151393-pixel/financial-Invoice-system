import { Button } from "../../../shared/components/Button";
import type { Workbench, WorkbenchQuery } from "../types/workbench";

export function WorkbenchTrendRange({
  data,
  change,
}: {
  data: Workbench;
  change: (patch: Partial<WorkbenchQuery>) => void;
}) {
  return (
    <div className="wb-trend-range">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          change({
            trendStart: String(form.get("trendStart") || "") || null,
            trendEnd: String(form.get("trendEnd") || "") || null,
          });
        }}
      >
        <label>
          开票开始日期
          <input type="date" name="trendStart" defaultValue={data.trendStart} />
        </label>
        <span aria-hidden="true">至</span>
        <label>
          开票结束日期
          <input type="date" name="trendEnd" defaultValue={data.trendEnd} />
        </label>
        <Button type="submit">查询趋势</Button>
        <Button onClick={() => change({ trendStart: null, trendEnd: null })}>本月</Button>
      </form>
      <p className="wb-caption">
        统计范围：{data.trendStart} 至 {data.trendEnd} · 最多查询 92 天<br />
        {data.latestInvoiceDate
          ? `已入库正常发票的最新开票日期：${data.latestInvoiceDate}`
          : "尚无已入库的正常发票开票日期"}
      </p>
    </div>
  );
}
