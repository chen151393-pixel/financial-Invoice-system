/** 同域请求与错误解析，业务模块不自行创建第二套请求客户端。 */
export class HttpError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "HttpError";
    this.status = status;
  }
}

export async function http<T>(path: string, method = "GET", value?: unknown): Promise<T> {
  let response: Response;
  let text: string;
  try {
    response = await fetch(`/api${path}`, {
      method,
      credentials: "same-origin",
      headers: value !== undefined ? { "Content-Type": "application/json" } : {},
      ...(value !== undefined ? { body: JSON.stringify(value) } : {}),
    });
    text = await response.text();
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    if (error instanceof TypeError) {
      throw new Error("无法连接服务或连接已中断，请检查网络及后端服务是否启动");
    }
    throw error;
  }
  const fallback = response.ok
    ? "服务返回的数据为空或格式异常，请联系管理员检查接口响应"
    : response.status >= 500
      ? `后端服务暂时不可用（HTTP ${response.status}），请确认后端已启动或联系管理员检查服务日志`
      : `请求失败（HTTP ${response.status}），请重新加载页面或联系管理员`;
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch (error) {
    // 代理可能返回空正文或 HTML，不能让解析错误掩盖 HTTP 失败，也不回显原始正文。
    if (error instanceof SyntaxError) throw new Error(fallback);
    throw error;
  }
  if (!response.ok) {
    const message =
      typeof data === "object" &&
      data !== null &&
      "error" in data &&
      typeof data.error === "string" &&
      data.error.trim()
        ? data.error
        : fallback;
    throw new HttpError(message, response.status);
  }
  if (data === null) throw new Error(fallback);
  return data as T;
}
