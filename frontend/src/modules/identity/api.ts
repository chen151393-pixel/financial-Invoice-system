import { http } from "../../shared/api/http";

export const getSession = () => http<{ authenticated: boolean }>("/session");
export const login = (username: string, password: string) =>
  http<{ authenticated: boolean }>("/session", "POST", { username, password });
export const logout = () => http<{ authenticated: boolean }>("/session", "DELETE");

// 兼容现有业务调用方：只检查会话，不再签发本机免密会话。
export const openLocalSession = getSession;
