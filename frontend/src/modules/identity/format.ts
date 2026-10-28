// 后端返回带 Z 的 UTC 时间，统一按北京时间显示。
export const formatTime = (value: string | null) =>
  value ? new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false }) : "—";
