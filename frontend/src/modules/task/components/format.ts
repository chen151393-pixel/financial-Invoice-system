// 后端返回 ISO 时间（UTC）；与同步页、合同文件夹一致，统一按北京时间显示。
export const formatTime = (value: string) =>
  new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" });
