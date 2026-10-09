import Demo from "../../app/page";
import InvoiceFollowup from "../../app/demo/pages/InvoiceFollowup";
import "../../app/globals.css";

export default function DemoPage() {
  if (new URLSearchParams(location.search).get("view") === "invoice-followup") return <InvoiceFollowup />;
  return <Demo />;
}
