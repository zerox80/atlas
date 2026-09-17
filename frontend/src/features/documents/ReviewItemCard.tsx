import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import api from "../../api";
import { invalidateDocumentAndTagQueries } from "../../queryKeys";
import { getApiErrorMessage } from "../../utils/errorUtils";
import { formatGermanNumber } from "../../utils/formatUtils";
import type { ReviewChange, ReviewItem } from "./reviewTypes";

const labels: Record<string, string> = {
  title: "Titel", description: "Beschreibung", value: "Betrag / Gesamtwert",
  annual_value: "Jahreswert", start_date: "Start-/Rechnungsdatum", end_date: "Enddatum",
  notice_period: "Kündigungsfrist (Tage)", tags: "Kategorien",
};
const statuses: Record<string, string> = {
  pending: "Ausstehend", processing: "Wird geprüft …", checked: "Keine Abweichung erkannt",
  issues: "Prüfbedarf", error: "Fehlgeschlagen", skipped: "Nicht geprüft",
  unavailable: "Nicht zugänglich", applied: "Korrekturen übernommen",
};
function valueText(value: ReviewChange["before"], field: string): string {
  if (value == null) return "Nicht belegt / leer";
  if (Array.isArray(value)) return value.join(", ") || "Keine";
  return typeof value === "number" && (field === "value" || field === "annual_value")
    ? `${formatGermanNumber(value)} €` : String(value);
}

export default function ReviewItemCard({ item, runId }: { item: ReviewItem; runId: string }) {
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const client = useQueryClient();
  const changes = item.result?.changes || [];
  const applicable = selected.filter(field => changes.some(change => change.field === field && change.can_apply));
  const apply = async () => {
    setBusy(true);
    setError("");
    try {
      await api.post(`/ai/reviews/${runId}/items/${item.id}/apply`, { fields: applicable });
      setSelected([]);
      await Promise.all([client.invalidateQueries(["document-reviews"]), invalidateDocumentAndTagQueries(client)]);
    } catch (err) {
      setError(getApiErrorMessage(err, "Korrekturen konnten nicht übernommen werden."));
    } finally { setBusy(false); }
  };
  return <article className="surface p-5">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p className="eyebrow">{item.document_type === "invoice" ? "Rechnung" : "Vertrag"}</p>
        <h2 className="mt-1 font-semibold break-words">{item.title}</h2>
      </div>
      <span className="chip">{statuses[item.status] || item.status}</span>
    </div>
    {item.contract_id && <Link className="mt-2 inline-block text-sm text-[#77a7ff] underline"
      to={`/${item.document_type === "invoice" ? "invoices" : "contracts"}?document_id=${item.contract_id}`}>Dokument öffnen</Link>}
    {item.error && <p className="mt-3 text-amber-200">{item.error}</p>}
    {item.result?.checked_files != null && <p className="mt-3 text-xs muted">{item.result.checked_files} PDF-Datei(en) geprüft, einschließlich PDF-Anlagen.</p>}
    {Boolean(item.result?.warnings?.length) && <ul className="mt-3 space-y-1 text-sm text-amber-200">
      {item.result!.warnings.map((warning, index) => <li key={index}>{warning}</li>)}
    </ul>}
    {Boolean(changes.length) && <div className="mt-4 overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead><tr className="border-b border-white/10 text-[#8f99a9]"><th className="p-2">Übernehmen</th><th className="p-2">Feld</th><th className="p-2">Gespeichert</th><th className="p-2">Neu erkannt</th></tr></thead>
        <tbody>{changes.map(change => <tr key={change.field} className="border-b border-white/5 align-top">
          <td className="p-2"><input type="checkbox" aria-label={`${labels[change.field]} übernehmen`}
            disabled={busy || !item.can_write || !change.can_apply} checked={selected.includes(change.field)}
            onChange={event => setSelected(current => event.target.checked ? [...current, change.field] : current.filter(field => field !== change.field))} /></td>
          <th className="p-2 font-medium">{labels[change.field]}</th>
          <td className="max-w-xs break-words p-2 muted">{valueText(change.before, change.field)}</td>
          <td className="max-w-xs break-words p-2">{valueText(change.after, change.field)}
            {!change.can_apply && <p className="mt-1 text-xs text-amber-200">Pflichtfeld – bitte manuell prüfen.</p>}</td>
        </tr>)}</tbody>
      </table>
    </div>}
    {item.result?.notice_period_evidence && <blockquote className="mt-4 border-l-2 border-[#b8f15a]/50 pl-3 text-sm muted">
      Beleg zur Kündigungsfrist: {item.result.notice_period_evidence}
    </blockquote>}
    {changes.length > 0 && item.can_write && <button className="btn-primary mt-4" disabled={busy || !applicable.length} onClick={() => void apply()}>
      {busy ? "Speichert …" : `${applicable.length} ausgewählte Korrektur(en) übernehmen`}
    </button>}
    {error && <p role="alert" className="mt-3 text-red-300">{error}</p>}
  </article>;
}
