import { http } from "../../shared/api/http";

export const openLocalSession = () => http<{ authenticated: boolean }>("/session/local", "POST", {});
