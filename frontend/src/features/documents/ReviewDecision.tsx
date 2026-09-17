import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import api from "../../api";
import { invalidateDocumentAndTagQueries } from "../../queryKeys";
import type { ReviewItem } from "./reviewTypes";
import { canApply, labels, valueText } from "./reviewPresentation";
import { reviewRequestError } from "./reviewRequestError";

export default function ReviewDecision({ item, runId }: { item: ReviewItem; runId: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [decision, setDecision] = useState(item.result?.decision);
  const client = useQueryClient();
  if (!item.result || item.result.legacy_report || !["issues", "hints", "checked", "applied"].includes(item.status)) return null;
  const changes = (item.result.changes || []).filter(canApply);
  const decide = async (accept: boolean) => {
    setBusy(true);
    setError("");
    try {
      await api.post(`/ai/reviews/${runId}/items/${item.id}/decision`, { accept });
      setDecision(accept ? "accepted" : "rejected");
      await Promise.all([client.invalidateQueries(["document-reviews"]), invalidateDocumentAndTagQueries(client)]);
    } catch (err) { setError(reviewRequestError(err, "Entscheidung konnte nicht gespeichert werden.")); }
    finally { setBusy(false); }
  };
  return <section className="mt-4 rounded-xl border border-[var(--line-strong)] p-4" aria-label="Dein Prüfvorschlag">
    <h3 className="font-semibold">{changes.length ? "Vorschlag: Diese Angaben aktualisieren" : "Vorschlag: Bestehende Angaben beibehalten"}</h3>
    {changes.length > 0 ? <ul className="my-3 space-y-1 text-sm">{changes.map(change => <li key={change.field}>
      {labels[change.field]}: {valueText(change.before, change.field)} → <strong>{valueText(change.after, change.field, change.currency)}</strong>
    </li>)}</ul> : <p className="my-3 text-sm muted">Die Prüfung hat keine ausreichend belegte Änderung gefunden. Deine gespeicherten Angaben bleiben erhalten.</p>}
    {(decision || item.result.decision) ? <p role="status" className="mt-3 text-sm">
      {(decision || item.result.decision) === "accepted" ? "Ja bestätigt · Vorschlag übernommen." : "Nein bestätigt · Angaben beibehalten."}
    </p> : <div className="mt-3 flex flex-wrap gap-2">
      <button className="btn-primary" disabled={busy || !item.can_write} onClick={() => void decide(true)}>
        {changes.length ? "Ja, Vorschlag übernehmen" : "Ja, Angaben beibehalten"}</button>
      <button className="btn-secondary" disabled={busy} onClick={() => void decide(false)}>Nein, Vorschlag ablehnen</button>
    </div>}
    {error && <p role="alert" className="mt-3 text-[var(--danger)]">{error}</p>}
  </section>;
}
