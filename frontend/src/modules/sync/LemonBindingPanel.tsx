import { useSearchParams } from "react-router";
import { useLemonBinding } from "./useLemonBinding";
import { LemonBindingView } from "./LemonBindingView";
import "./lemon-binding.css";

export function LemonBindingPanel() {
  const binding = useLemonBinding();
  const [params] = useSearchParams();
  return <LemonBindingView {...binding} invalidCallback={params.get("binding") === "invalid"} />;
}
