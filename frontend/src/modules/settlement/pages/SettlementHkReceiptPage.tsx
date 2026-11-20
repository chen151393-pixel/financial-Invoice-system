import { useId, useRef, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router";
import { paths, settlementBatchListPath, settlementHkRegistrationPath } from "../../../app/paths";
import { readImportFile } from "../../../shared/api/import-file";
import { HttpError } from "../../../shared/api/http";
import { Alert } from "../../../shared/components/ui";
import { registerHkReceipt } from "../api/hk-receipt-api";
import { HkReceiptSelection } from "../components/HkReceiptSelection";
import { HkReceiptFields } from "../components/HkReceiptFields";
import { HkReceiptReconciliation } from "../components/HkReceiptReconciliation";
import { useHkRegistrationCheck } from "../hooks/useHkRegistrationCheck";
import { clearHkReceiptDraft, readHkReceiptDraft, saveHkReceiptDraft } from "../hooks/hkReceiptDraftStore";
import type { HkReceiptFields as Fields, BankSlipUpload } from "../types/hk-receipt";
import "../components/hk-receipt.css";

export function SettlementHkReceiptPage() {
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const numbers = params.getAll("declarationNo");
  const [requestId] = useState(() => params.get("draft") || crypto.randomUUID());
  const [initial] = useState(() => readHkReceiptDraft(requestId));
  const [fields, setFields] = useState<Fields>(
    initial?.fields || {
      receivedOn: "",
      receivedAmount: "",
      receivedFee: "0",
      payer: null,
      receivingAccount: "",
      receivedReference: "",
      note: "",
    },
  );
  const [bankSlip, setBankSlip] = useState<BankSlipUpload | null>(initial?.bankSlip || null);
  const [busy, setBusy] = useState(false);
  const [readingFile, setReadingFile] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Readonly<Record<string, string>>>({});
  const submitting = useRef(false);
  const formRef = useRef<HTMLFormElement>(null);
  const formId = useId();
  const context = useHkRegistrationCheck(numbers, "0", "0", "");
  const check = useHkRegistrationCheck(numbers, fields.receivedAmount, fields.receivedFee, fields.receivedOn);
  const payer = fields.payer ?? context.result?.consignee ?? "";
  const state = location.state as { hkReturnTo?: string } | null;
  const returnTo = state?.hkReturnTo?.startsWith(paths.settlementHk)
    ? state.hkReturnTo
    : `${paths.settlementHk}?stage=register`;
  const change = (key: keyof Fields, value: string) =>
    setFields((previous) => ({ ...previous, [key]: value }));
  function saveDraft() {
    saveHkReceiptDraft({ id: requestId, fields: { ...fields, payer }, bankSlip });
  }
  function reselect() {
    saveDraft();
    navigate(returnTo, {
      state: {
        hkReceiptDraftId: requestId,
        hkSelection: context.result?.rows.filter((row) => numbers.includes(row.declarationNo)) || [],
      },
    });
  }
  function remove(number: string) {
    navigate(
      settlementHkRegistrationPath(
        numbers.filter((value) => value !== number),
        requestId,
      ),
      { replace: true, state: location.state },
    );
  }
  async function chooseSlip(file: File) {
    setReadingFile(true);
    setError("");
    try {
      const uploaded = await readImportFile(file);
      setBankSlip({ fileName: uploaded.filename, content: uploaded.content });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "水单文件读取失败，请重新选择");
    } finally {
      setReadingFile(false);
    }
  }
  async function submit() {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    setFieldErrors({});
    try {
      const batch = await registerHkReceipt({
        requestId: requestId,
        declarationNos: numbers,
        receivedOn: fields.receivedOn,
        receivedAmount: fields.receivedAmount,
        receivedFee: fields.receivedFee || "0",
        payer,
        receivingAccount: fields.receivingAccount,
        receivedReference: fields.receivedReference,
        note: fields.note,
        bankSlip,
      });
      clearHkReceiptDraft(requestId);
      navigate(settlementBatchListPath("", batch.batchNo), { replace: true });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "登记失败，填写内容已保留");
      if (reason instanceof HttpError) {
        setFieldErrors(reason.fieldErrors);
        const field = formRef.current?.elements.namedItem(Object.keys(reason.fieldErrors)[0] || "");
        if (field instanceof HTMLInputElement) requestAnimationFrame(() => field.focus());
      }
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return (
    <div className="hk-receipt-page">
      <form
        ref={formRef}
        id={formId}
        className="hk-receipt__main"
        aria-busy={busy}
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <HkReceiptSelection
          numbers={numbers}
          data={context.result}
          loading={context.loading}
          busy={busy || readingFile}
          onRemove={remove}
          onReselect={reselect}
        />
        {context.error && (
          <Alert tone="danger" title="已选报关单核对失败">
            {context.error}
          </Alert>
        )}
        <HkReceiptFields
          fields={fields}
          payer={payer}
          currency={context.result?.currency || ""}
          accounts={context.result?.accounts || []}
          busy={busy}
          readingFile={readingFile}
          errors={fieldErrors}
          bankSlip={bankSlip}
          onChange={change}
          onFile={(file) => void chooseSlip(file)}
        />
        {error && (
          <Alert tone="danger" title="登记未完成，填写内容已保留">
            {error}
          </Alert>
        )}
      </form>
      <HkReceiptReconciliation
        data={check.result}
        loading={check.loading}
        error={check.error}
        busy={busy || readingFile}
        formId={formId}
        onCancel={() => {
          clearHkReceiptDraft(requestId);
          navigate(returnTo);
        }}
      />
    </div>
  );
}
