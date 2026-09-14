/** 同域请求与错误解析，业务模块不自行创建第二套请求客户端。 */
export async function http<T>(path: string, method = "GET", value?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    credentials: "same-origin",
    headers: value !== undefined ? { "Content-Type": "application/json" } : {},
    ...(value !== undefined ? { body: JSON.stringify(value) } : {}),
  });
  const data: unknown = await response.json();
  if (!response.ok) {
    const message =
      typeof data === "object" && data !== null && "error" in data && typeof data.error === "string"
        ? data.error
        : `请求失败 ${response.status}`;
    throw new Error(message);
  }
  return data as T;
}
