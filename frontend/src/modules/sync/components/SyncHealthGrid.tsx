import { useEffect, useState } from "react";
import { Button, Card, CardContent, CardHeader, ErrorState, Skeleton } from "../../../shared/components/ui";
import { getSyncHealth } from "../api/health-api";
import type { SyncHealth } from "../types/health";
import "./sync-health.css";

const LEGEND = [
  ["success", "全部成功"],
  ["partial", "部分成功"],
  ["failed", "失败"],
  ["running", "执行中"],
  ["none", "未执行"],
] as const;

/** 近 14 天同步情况：每行一个来源、每格一天，格子悬停与读屏均给出当天执行次数与结果。 */
export function SyncHealthGrid() {
  const [data, setData] = useState<SyncHealth | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    getSyncHealth().then(
      (value) => active && setData(value),
      (reason: unknown) => active && setError(reason instanceof Error ? reason.message : "同步情况读取失败"),
    );
    return () => {
      active = false;
    };
  }, [attempt]);
  return (
    <Card className="sync-health" aria-labelledby="sync-health-title">
      <CardHeader
        title={<span id="sync-health-title">近 14 天同步情况</span>}
        description="每格一天（北京时间），含定时与手动执行"
        actions={
          <ul className="sync-health__legend" aria-label="图例">
            {LEGEND.map(([status, label]) => (
              <li key={status}>
                <span className="sync-health__cell" data-status={status} aria-hidden="true" />
                {label}
              </li>
            ))}
          </ul>
        }
      />
      <CardContent>
        {!data && !error && <Skeleton rows={2} label="正在读取同步情况" />}
        {error && (
          <ErrorState
            title="同步情况暂时无法读取"
            message={error}
            action={
              <Button
                onClick={() => {
                  setError("");
                  setAttempt((value) => value + 1);
                }}
              >
                重新读取
              </Button>
            }
          />
        )}
        {data && (
          <div className="sync-health__scroll">
            <table className="sync-health__table">
              <caption className="sync-health__sr">近 14 天各来源每天的同步结果</caption>
              <thead>
                <tr>
                  <th scope="col">来源</th>
                  {data.dates.map((date) => (
                    <th scope="col" key={date}>
                      {Number(date.slice(8))}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row) => (
                  <tr key={row.key}>
                    <th scope="row">{row.label}</th>
                    {row.days.map((day) => {
                      const text = `${row.label} ${day.date}：${day.label}${
                        day.runs ? `，执行 ${day.runs} 次${day.failed ? `，失败 ${day.failed} 次` : ""}` : ""
                      }`;
                      return (
                        <td key={day.date}>
                          <span
                            className="sync-health__cell"
                            data-status={day.status}
                            role="img"
                            aria-label={text}
                            title={text}
                          />
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
