/** 仅格式化单价展示；按十进制字符串四舍五入，不改变后端原值或核对结论。 */
export function formatUnitPrice(value: string | null | undefined): string {
  if (!value) return "未提供";
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value);
  if (!match) return "未提供";

  const [, sign, integer, fraction = ""] = match;
  const digits = fraction.padEnd(3, "0");
  const rounded = BigInt(`${integer}${digits.slice(0, 2)}`) + (digits[2] >= "5" ? 1n : 0n);
  const fixed = rounded.toString().padStart(3, "0");
  return `${rounded === 0n ? "" : sign}${fixed.slice(0, -2)}.${fixed.slice(-2)}`;
}
