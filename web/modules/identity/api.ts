import { http } from "../../shared/api/http";

export const login = (username: string, password: string) =>
  http<{ authenticated: boolean }>("/session", "POST", { username, password });
export const logout = () => http<{ authenticated: boolean }>("/session", "DELETE");
