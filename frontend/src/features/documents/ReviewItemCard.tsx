import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import api from "../../api";
import { invalidateDocumentAndTagQueries } from "../../queryKeys";
import { reviewRequestError } from "./reviewRequestError";
import type { ReviewItem } from "./reviewTypes";
import { applyBlockedReason, canApply, labels, stageLabels, valueText } from "./reviewPresentation";
import { FieldFinding, ReviewEvidence } from "./ReviewFindings";
import ReviewProgress from "./ReviewProgress";
import ReviewDecision from "./ReviewDecision";
import ReviewSplitProposal from "./ReviewSplitProposal";

const statuses: Record<string, string> = {
  pending: "Ausstehend", processing: "Wird geprüft …", checked: "Kein Widerspruch erkannt", hints: "Hinweise / Ergänzungen",
  issues: "Prüfbedarf", error: "Fehlgeschlagen", skipped: "Nicht geprüft",
  unavailable: "Nicht zugänglich", applied: "Korrekturen übernommen",
};

export default function ReviewItemCard({ item, runId }: { item: ReviewItem; runId: string }) {
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const client = useQueryClient();
  const changes = (item.result?.changes || []).filter(change => change.status !== "NOT_EVIDENCED");
  const unmentioned = item.result?.checks?.filter(check => check.status === "NOT_EVIDENCED") || [];
  const confirmed = item.result?.checks?.filter(check => check.status === "CONFIRMED") || [];
  const diagnostic = item.result?.diagnostic;
  const applicable = selected.filter(field => changes.some(change => change.field === field && canApply(change)));
  const apply = async () => {
    setBusy(true);
    setError("");
    try {
      await api.post(`/ai/reviews/${runId}/items/${item.id}/apply`, { fields: applicable });
      setSelected([]);
      await Promise.all([client.invalidateQueries(["document-reviews"]), invalidateDocumentAndTagQueries(client)]);
    } catch (err) {
      setError(reviewRequestError(err, "Korrekturen konnten nicht übernommen werden."));
    } finally { setBusy(false); }
  };
  return <article className="surface min-w-0 p-4 sm:p-5">
    <div className="flex flex-col items-start gap-3 sm:flex-row sm:justify-between">
      <div className="min-w-0 flex-1">
        <p className="eyebrow">{item.document_type === "invoice" ? "Rechnung" : "Vertrag"}</p>
        <h2 className="mt-1 font-semibold break-words">{item.title}</h2>
      </div>
      <span className="chip" style={{ color: item.status === "error" ? "var(--danger)" : item.status === "issues" ? "var(--warning)" : undefined }}>
        {statuses[item.status] || item.status}</span>
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
    <ReviewDecision item={item} runId={runId} />
    <ReviewSplitProposal key={`${item.id}-${item.result?.split_proposals?.length || 0}`} item={item} runId={runId} />
    {item.result?.legacy_report && <p className="mt-3 text-sm text-[var(--warning)]">Älterer Prüfbericht aus dem vorherigen Prüfverfahren.
      Für belegte Vorschläge bitte einen neuen Prüflauf starten.</p>}
    {item.result?.checked_files != null && <p className="mt-3 text-xs muted">{item.result.checked_files} PDF-Datei(en) geprüft, einschließlich PDF-Anlagen.</p>}
    {Boolean(item.result?.warnings?.length) && <ul className="mt-3 space-y-1 text-sm text-[var(--warning)]">
      {item.result!.warnings!.map((warning, index) => <li key={index}>{warning}</li>)}
    </ul>}
    {Boolean(changes.length) && !item.result?.decision && <details className="mt-5 space-y-4">
      <summary className="cursor-pointer text-sm">Belege ansehen und Änderungen einzeln auswählen</summary>
      {changes.map(change => {
        const blocked = applyBlockedReason(change, Boolean(item.result?.legacy_report), Boolean(item.can_write));
        const reasonId = `review-${item.id}-${change.field}-blocked`;
        return <section key={change.field} aria-label={`${labels[change.field]} prüfen`}
        className="rounded-xl border border-[var(--line)] p-3 sm:p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold">{labels[change.field]}</h3>
          <label className="flex min-h-8 items-center gap-2 text-sm">
            <input type="checkbox" className="h-4 w-4 accent-[var(--accent)]" aria-label={`${labels[change.field]} übernehmen`}
              aria-describedby={blocked ? reasonId : undefined}
              disabled={busy || Boolean(blocked)} checked={!blocked && selected.includes(change.field)}
              onChange={event => setSelected(current => event.target.checked ? [...current, change.field] : current.filter(field => field !== change.field))} />
            Übernehmen</label>
        </div>
        {blocked && <p id={reasonId} className="mb-3 text-sm muted">Übernahme gesperrt: {blocked}</p>}
        <div className="grid gap-4 text-sm lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.5fr)]">
          <div className="min-w-0 break-words"><p className="mb-1 text-xs muted">Gespeichert</p>{valueText(change.before, change.field)}</div>
          <div className="min-w-0 break-words"><p className="mb-1 text-xs muted">Dokumentangabe</p>{valueText(change.after, change.field, change.currency)}</div>
          <div className="min-w-0 break-words"><FieldFinding change={change} /></div>
        </div>
      </section>;
      })}
      {changes.some(canApply) && item.can_write && !item.result?.legacy_report && <button className="btn-primary mt-4" disabled={busy || !applicable.length} onClick={() => void apply()}>
        {busy ? "Speichert …" : `${applicable.length} ausgewählte Korrektur(en) übernehmen`}
      </button>}
    </details>}
    {unmentioned.length > 0 && <details className="mt-4 text-sm muted"><summary className="cursor-pointer">
      {unmentioned.length} {unmentioned.length === 1 ? "Feld" : "Felder"} im Dokument nicht belegt · gespeicherte Werte bleiben erhalten</summary>
      <dl className="mt-3 grid gap-2 sm:grid-cols-2">{unmentioned.map(change => <div key={change.field}>
        <dt>{labels[change.field]}</dt><dd>{valueText(change.before, change.field)}</dd></div>)}</dl>
    </details>}
    {confirmed.length > 0 && <details className="mt-4 text-sm muted"><summary>{confirmed.length} bestätigte Felder</summary>
      {confirmed.map(change => <div key={change.field} className="mt-3"><strong>{labels[change.field]}</strong><FieldFinding change={change} /></div>)}
    </details>}
    <ReviewEvidence result={item.result} />
    {item.result?.notice_period_evidence && <blockquote className="mt-4 border-l-2 border-[#b8f15a]/50 pl-3 text-sm muted">
      Beleg zur Kündigungsfrist: {item.result.notice_period_evidence}
    </blockquote>}
    {error && <p role="alert" className="mt-3 text-red-300">{error}</p>}
  </article>;
}
