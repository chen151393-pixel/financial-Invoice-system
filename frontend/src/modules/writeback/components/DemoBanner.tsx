import { paths } from "../../../app/paths";
import { DEMO_TITLES, demoSet, type DemoSet } from "../demo/demo-mode";

const sets: DemoSet[] = ["1", "2"];

/** 演示数据模式的醒目标识：说明数据来源与影响范围，并提供切换数据集和退出入口。 */
export function DemoBanner() {
  const set = demoSet();
  if (!set) return null;
  return (
    <section className="wb-demo" role="status" aria-label="演示数据说明">
      <strong>当前为演示数据</strong>
      <span>{DEMO_TITLES[set]}。数据只在本页面内模拟，不连接后端，不会写入 NS；刷新页面恢复初始数据。</span>
      <span className="wb-demo__links">
        {sets
          .filter((value) => value !== set)
          .map((value) => (
            <a key={value} href={`${paths.writeback}?demo=${value}`}>
              切换到演示数据{value === "1" ? "一" : "二"}
            </a>
          ))}
        <a href={`${paths.writeback}?demo=0`}>退出演示</a>
      </span>
    </section>
  );
}
