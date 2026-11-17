import { useSession } from "../modules/identity/session-context";
import { customsDeclarationPath, financeDeclarationPath, taskPath } from "./paths";

export function useReviewLinks() {
  const pages = useSession().user?.pages;
  return {
    finance: pages?.includes("finance") ? financeDeclarationPath : undefined,
    customs: pages?.includes("customs-match") ? customsDeclarationPath : undefined,
    task: pages?.includes("invoice-followup") ? taskPath : undefined,
  };
}
