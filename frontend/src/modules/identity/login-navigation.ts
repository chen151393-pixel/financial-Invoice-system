import { paths } from "../../app/paths";

/** 回跳只允许站内地址；防止外部跳转和反复跳回登录页。 */
export function getLoginDestination(state: unknown): string {
  const value =
    typeof state === "object" && state !== null && "from" in state && typeof state.from === "string"
      ? state.from
      : null;
  if (!value || !value.startsWith("/") || value.startsWith("//") || /[\\\s]/.test(value)) {
    return paths.pl;
  }
  try {
    const url = new URL(value, "https://workspace.invalid");
    const pathname = decodeURIComponent(url.pathname).replace(/\/+$/, "").toLowerCase();
    if (url.origin !== "https://workspace.invalid" || pathname === paths.login) return paths.pl;
    return value;
  } catch (error) {
    if (error instanceof TypeError || error instanceof URIError) return paths.pl;
    throw error;
  }
}
