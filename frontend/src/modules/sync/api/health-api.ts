import { http } from "../../../shared/api/http";
import type { SyncHealth } from "../types/health";

/** 近 14 天各来源每天的执行结果（后端按北京时间汇总）。 */
export const getSyncHealth = () => http<SyncHealth>("/sync/health");
