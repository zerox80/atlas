import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import api from "../../api";
import { invalidateDocumentAndTagQueries } from "../../queryKeys";
import { FieldFinding } from "./ReviewFindings";
import { labels, recommendationFor, recommendationReason, valueText } from "./reviewPresentation";
import { reviewRequestError } from "./reviewRequestError";
import type { ReviewChange, ReviewItem } from "./reviewTypes";

const proposalKey = (change: ReviewChange) => JSON.stringify([change.field, change.before, change.after]);

export default function ReviewSuggestions({ item, runId }: { item: ReviewItem; runId: string }) {
  const [selected, setSelected] = useState<string[]>([]);
  const [applied, setApplied] = useState<string[]>([]);
  const [savedFields, setSavedFields] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const client = useQueryClient();
  const fields = Array.from(new Map([...(item.result?.checks || []), ...(item.result?.changes || [])]
    .map(change => [change.field, change])).values());
  const remaining = fields.filter(change => !applied.includes(proposalKey(change)));
  const proposals = remaining.filter(change => recommendationFor(change) === "update");
  const unchanged = remaining.filter(change => recommendationFor(change) !== "update");
  const selectable = Boolean(item.can_write && !item.result?.legacy_report && !item.result?.decision);
  const chosen = proposals.filter(change => selectable && selected.includes(proposalKey(change)));
  const apply = async () => {
    if (busy || !chosen.length) return;
    setBusy(true);
    setError("");
    try {
      await api.post(`/ai/reviews/${runId}/items/${item.id}/apply`, { fields: chosen.map(change => change.field) });
      setApplied(current => [...current, ...chosen.map(proposalKey)]);
      setSavedFields(chosen.map(change => change.field));
      setSelected([]);
      await Promise.all([client.invalidateQueries(["document-reviews"]), invalidateDocumentAndTagQueries(client)]);
    } catch (err) {
      setError(reviewRequestError(err, "Änderungen konnten nicht übernommen werden."));
    } finally { setBusy(false); }
  };

  if (!item.result || (!fields.length && !["checked", "applied"].includes(item.status))) return null;
  return <div className="mt-5 space-y-4">
    {proposals.length > 0 && <section aria-label="Änderungsvorschläge" className="space-y-3">
      <h3 className="font-semibold">{proposals.length} {proposals.length === 1 ? "Änderung vorgeschlagen" : "Änderungen vorgeschlagen"}</h3>
      {selectable && <p className="text-sm muted">Wähle die Änderungen aus, die du übernehmen möchtest.</p>}
      {!item.can_write && <p className="text-sm muted">Nur Ansicht: Du hast keine Schreibberechtigung für dieses Dokument.</p>}
      {item.result.decision && <p className="text-sm muted">{item.result.decision === "accepted"
        ? "Dieser Prüfvorschlag wurde bereits übernommen." : "Dieser Prüfvorschlag wurde bereits abgelehnt. Die Angaben wurden beibehalten."}</p>}
      {proposals.map(change => <section key={change.field} aria-label={`${labels[change.field] || change.field} ändern`}
        className="rounded-xl border border-[var(--line-strong)] p-3 sm:p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h4 className="font-semibold">{labels[change.field] || change.field}</h4>
          {selectable && <label className="flex min-h-8 cursor-pointer items-center gap-2 text-sm">
            <input type="checkbox" className="h-4 w-4 accent-[var(--accent)]"
              aria-label={`${labels[change.field] || change.field} übernehmen`} disabled={busy}
              checked={selected.includes(proposalKey(change))}
              onChange={event => setSelected(current => event.target.checked
                ? [...current, proposalKey(change)] : current.filter(key => key !== proposalKey(change)))} />
            Ja, übernehmen</label>}
        </div>
        <div className="grid items-center gap-2 text-sm sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
          <div className="min-w-0 break-words"><p className="mb-1 text-xs muted">Gespeichert</p>{valueText(change.before, change.field)}</div>
          <span aria-hidden="true" className="muted">→</span>
          <div className="min-w-0 break-words"><p className="mb-1 text-xs muted">Vorgeschlagen</p><strong>{valueText(change.after, change.field, change.currency)}</strong></div>
        </div>
        <p className="mt-3 text-sm">{recommendationReason(change)}</p>
        <details className="mt-3 text-sm muted"><summary className="cursor-pointer">Beleg und Einordnung</summary>
          <div className="mt-2"><FieldFinding change={change} /></div>
        </details>
      </section>)}
      {selectable && <button className="btn-primary" disabled={busy || !chosen.length} onClick={() => void apply()}>
        {busy ? "Speichert …" : `Ausgewählte Änderungen übernehmen (${chosen.length})`}
      </button>}
    </section>}
    {savedFields.length > 0 && <p role="status" className="text-sm">Übernommen: {savedFields.map(field => labels[field] || field).join(", ")}.</p>}
    {!proposals.length && <p className="font-medium">{savedFields.length || item.status === "applied"
      ? "Keine weiteren Änderungen empfohlen." : "Keine Änderung empfohlen."}</p>}
    {unchanged.length > 0 && <section aria-label="Empfehlungen für unveränderte Angaben" className="rounded-xl border border-[var(--line)] p-3 sm:p-4">
      <h3 className="font-semibold">Diese Angaben bleiben erhalten</h3>
      <dl className="mt-3 space-y-4">{unchanged.map(change => <div key={change.field}>
        <dt className="text-sm font-medium">{labels[change.field] || change.field}: {recommendationFor(change) === "leave_empty"
          ? "Leer lassen" : `${valueText(change.before, change.field)} beibehalten`}</dt>
        <dd className="mt-1 text-sm muted">
          <p>{recommendationReason(change)}</p>
          {change.after != null && JSON.stringify(change.before) !== JSON.stringify(change.after) && <p className="mt-1">
            Nicht zur Übernahme empfohlen: {valueText(change.after, change.field, change.currency)}</p>}
          {change.evidence && <details className="mt-2"><summary className="cursor-pointer">Beleg und Einordnung</summary>
            <div className="mt-2"><FieldFinding change={change} /></div>
          </details>}
        </dd>
      </div>)}</dl>
    </section>}
    {error && <p role="alert" className="text-sm text-[var(--danger)]">{error}</p>}
  </div>;
}
