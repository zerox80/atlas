import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import api from "../../api";
import { invalidateDocumentAndTagQueries } from "../../queryKeys";
import type { ReviewItem } from "./reviewTypes";
import { valueText } from "./reviewPresentation";
import { reviewRequestError } from "./reviewRequestError";

export default function ReviewSplitProposal({ item, runId, onResolved }: {
  item: ReviewItem; runId: string; onResolved: () => void;
}) {
  const proposals = item.result?.split_proposals || [];
  const [selected, setSelected] = useState<number[]>(proposals.map((_, index) => index));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState(item.result?.split_created);
  const [declined, setDeclined] = useState(item.result?.split_declined);
  const client = useQueryClient();
  const done = created || item.result?.split_created;
  if (item.result?.legacy_report || (!done && proposals.length < 2)) return null;
  const decide = async (accept: boolean) => {
    setBusy(true);
    setError("");
    try {
      const response = await api.post(`/ai/reviews/${runId}/items/${item.id}/split`, { accept, selected: accept ? selected : [] });
      if (accept || response.data.already_created) setCreated(response.data.created);
      else setDeclined(true);
      onResolved();
      await Promise.all([client.invalidateQueries(["document-reviews"]), invalidateDocumentAndTagQueries(client)]);
    } catch (err) { setError(reviewRequestError(err, "Aufteilung konnte nicht gespeichert werden.")); }
    finally { setBusy(false); }
  };
  return <section className="mt-4 rounded-xl border border-[var(--line-strong)] p-4" aria-label="Dokumente aufteilen">
    <h3 className="font-semibold">Vorschlag: Eigenständige Dokumente getrennt anlegen</h3>
    {done ? <div role="status" className="mt-3 space-y-2">
      <p>Aufteilung erstellt. Das Original bleibt erhalten.</p>
      {done.map(entry => <p key={entry.id}><Link className="text-[#77a7ff] underline"
        to={`/${entry.document_type === "invoice" ? "invoices" : "contracts"}?document_id=${entry.id}`}>{entry.title}</Link></p>)}
    </div> : (declined || item.result?.split_declined) ? <p role="status" className="mt-3">Nein bestätigt · Dokumente bleiben zusammen.</p> : <>
      <p className="my-3 text-sm muted">Jeder ausgewählte Eintrag erhält eine eigene PDF aus den angegebenen Seiten.
        Das Original bleibt zusätzlich in der Liste; sein Betrag wird durch die Aufteilung nicht geändert.
        Neue Einträge zählen mit ihren eigenen Beträgen in den jeweiligen Summen mit.</p>
      <div className="space-y-3">{proposals.map((proposal, index) => <div key={index} className="rounded-lg border border-[var(--line)] p-3">
        <label className="flex items-start gap-2 font-medium"><input type="checkbox" className="mt-1 accent-[var(--accent)]"
          checked={selected.includes(index)} disabled={busy || !item.can_write}
          onChange={event => setSelected(current => event.target.checked ? [...current, index] : current.filter(value => value !== index))} />
          {proposal.title}</label>
        <p className="mt-2 text-sm">{proposal.document_type === "invoice" ? "Rechnung" : "Vertrag"} · Gesamtbrutto: {valueText(proposal.values.value ?? null, "value", "EUR")}</p>
        <p className="mt-1 text-sm muted">{proposal.reason}</p>
        <p className="mt-1 text-xs muted">{proposal.pages.map(part =>
          `${item.result?.progress?.files?.[part.document - 1]?.name || `PDF ${part.document}`} · Seite ${part.page}`).join("; ")}</p>
        <details className="mt-2 text-sm"><summary className="cursor-pointer">Beleg ansehen</summary><blockquote>{proposal.evidence.quote}</blockquote></details>
      </div>)}</div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button className="btn-primary" disabled={busy || !item.can_write || !selected.length} onClick={() => void decide(true)}>
          Ja, {selected.length} {selected.length === 1 ? "Eintrag" : "Einträge"} mit eigenen PDFs erstellen</button>
        <button className="btn-secondary" disabled={busy} onClick={() => void decide(false)}>Nein, zusammenlassen</button>
      </div>
    </>}
    {error && <p role="alert" className="mt-3 text-[var(--danger)]">{error}</p>}
  </section>;
}
