import { Link } from "react-router-dom";
import type { ReviewItem } from "./reviewTypes";
import { canApply, stageLabels } from "./reviewPresentation";
import { ReviewEvidence } from "./ReviewFindings";
import ReviewProgress from "./ReviewProgress";
import ReviewSuggestions from "./ReviewSuggestions";
import ReviewSplitProposal from "./ReviewSplitProposal";

const statuses: Record<string, string> = {
  pending: "Ausstehend", processing: "Wird geprüft …", checked: "Prüfung abgeschlossen", hints: "Empfehlungen vorhanden",
  issues: "Empfehlungen vorhanden", error: "Fehlgeschlagen", skipped: "Nicht geprüft",
  unavailable: "Nicht zugänglich", applied: "Änderungen übernommen",
};

export default function ReviewItemCard({ item, runId }: { item: ReviewItem; runId: string }) {
  const diagnostic = item.result?.diagnostic;
  const complete = ["issues", "hints", "checked", "applied"].includes(item.status);
  const hasSuggestions = complete && (item.result?.changes || []).some(canApply) && !item.result?.decision;
  return <article className="surface min-w-0 p-4 sm:p-5">
    <div className="flex flex-col items-start gap-3 sm:flex-row sm:justify-between">
      <div className="min-w-0 flex-1">
        <p className="eyebrow">{item.document_type === "invoice" ? "Rechnung" : "Vertrag"}</p>
        <h2 className="mt-1 font-semibold break-words">{item.title}</h2>
      </div>
      <span className="chip" style={{ color: item.status === "error" ? "var(--danger)" : item.status === "issues" ? "var(--warning)" : undefined }}>
        {hasSuggestions ? "Änderungsvorschläge" : statuses[item.status] || item.status}</span>
    </div>
    {item.contract_id && <Link className="mt-2 inline-block text-sm text-[#77a7ff] underline"
      to={`/${item.document_type === "invoice" ? "invoices" : "contracts"}?document_id=${item.contract_id}`}>Dokument öffnen</Link>}
    {item.error && <p className="mt-3 text-[var(--danger)]">{item.error}</p>}
    {diagnostic && <div className="mt-3 break-words rounded-lg border border-[var(--line-strong)] p-3 text-sm" role="note" aria-label="Fehlerdetails">
      <p><strong>{diagnostic.code}</strong> · {stageLabels[diagnostic.stage] || diagnostic.stage}
        {diagnostic.http_status && ` · HTTP ${diagnostic.http_status}`}</p>
      {!item.error && <p>{diagnostic.message}</p>}
      {diagnostic.validation_issues?.map(issue => <p key={issue} className="mt-1 font-mono text-xs">{issue}</p>)}
      <p className="mt-1 text-xs muted">{diagnostic.exception_type && `Fehlerklasse: ${diagnostic.exception_type} · `}
        Analysemodell: {item.result?.model || "unbekannt"} · OCR-Modell: {item.result?.ocr_model || "unbekannt"}</p>
    </div>}
    <ReviewProgress item={item} />
    {complete && <ReviewSuggestions key={`${runId}-${item.id}`} item={item} runId={runId} />}
    <ReviewSplitProposal key={`${item.id}-${item.result?.split_proposals?.length || 0}`} item={item} runId={runId} />
    {item.result?.legacy_report && <p className="mt-3 text-sm text-[var(--warning)]">Älterer Prüfbericht aus dem vorherigen Prüfverfahren.
      Für belegte Vorschläge bitte einen neuen Prüflauf starten.</p>}
    {item.result?.checked_files != null && <p className="mt-3 text-xs muted">{item.result.checked_files} PDF-Datei(en) geprüft, einschließlich PDF-Anlagen.</p>}
    {Boolean(item.result?.warnings?.length) && <ul className="mt-3 space-y-1 text-sm text-[var(--warning)]">
      {item.result!.warnings!.map((warning, index) => <li key={index}>{warning}</li>)}
    </ul>}
    <ReviewEvidence result={item.result} />
    {item.result?.notice_period_evidence && <blockquote className="mt-4 border-l-2 border-[#b8f15a]/50 pl-3 text-sm muted">
      Beleg zur Kündigungsfrist: {item.result.notice_period_evidence}
    </blockquote>}
  </article>;
}
