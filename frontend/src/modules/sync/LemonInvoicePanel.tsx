import { LemonInvoiceView } from "./LemonInvoiceView";
import { useLemonInvoices } from "./useLemonInvoices";
import "./lemon-invoices.css";

export function LemonInvoicePanel() {
  return <LemonInvoiceView {...useLemonInvoices()} />;
}
