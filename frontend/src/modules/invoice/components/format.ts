// 只调整十进制字符串的展示（千分位、补足两位小数），不转换浮点、不计算金额。
export const money = (value: string | null) => {
  if (value === null) return "—";
  const [integer, fraction = ""] = value.split(".");
  return `${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${fraction.replace(/0+$/, "").padEnd(2, "0")}`;
};
export const shown = (value: string | null | undefined) => value || "—";
