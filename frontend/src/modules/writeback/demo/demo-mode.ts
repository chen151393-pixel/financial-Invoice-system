/**
 * 演示数据开关：只有地址带 ?demo=1 或 ?demo=2 时启用，?demo=0 退出；
 * 本标签页内记住所选数据集，切换列表与详情时不丢失。正常访问不受影响。
 */
export type DemoSet = "1" | "2";

const KEY = "writeback-demo-set";
const valid = (value: string | null): value is DemoSet => value === "1" || value === "2";

export function demoSet(): DemoSet | null {
  if (typeof window === "undefined") return null;
  const param = new URLSearchParams(window.location.search).get("demo");
  try {
    if (valid(param)) window.sessionStorage.setItem(KEY, param);
    else if (param === "0") window.sessionStorage.removeItem(KEY);
    const stored = window.sessionStorage.getItem(KEY);
    return valid(stored) ? stored : null;
  } catch {
    // 浏览器禁用存储时只看当前地址。
    return valid(param) ? param : null;
  }
}

/** 横幅上的数据集说明；放在这里而不是数据文件中，正常页面不会加载演示数据。 */
export const DEMO_TITLES: Record<DemoSet, string> = {
  "1": "演示数据一：每种回写状态各一张发票，确认后演示写入成功",
  "2": "演示数据二：多账单、外币与校验未通过等情况，确认后演示 NS 超时待核实",
};
