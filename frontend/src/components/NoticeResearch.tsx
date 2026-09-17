import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FiGlobe, FiSearch } from "react-icons/fi";
import api from "../api";
import { getApiErrorMessage } from "../utils/errorUtils";

interface ResearchResult {
  query: string;
  answer: string;
  sources: { title: string; url: string }[];
  provider: string;
  model: string;
}

/** Intentionally receives no document, title, description, or chat props. */
export default function NoticeResearch() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ResearchResult | null>(null);
  const status = useQuery(
    ["notice-research-status"],
    async () => (await api.get<{ available: boolean; provider: string; model: string; reason?: string }>("/ai/notice-research")).data,
    { enabled: open, staleTime: 60_000 },
  );
  const search = async () => {
    if (busy || !confirmed || !status.data?.available) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const response = await api.post<ResearchResult>("/ai/notice-research", {
        query: query.trim(), confirmed_public: true,
      }, { timeout: 135_000 });
      setResult(response.data);
    } catch (err) {
      setError(getApiErrorMessage(err, "Webrecherche fehlgeschlagen."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="mt-3 text-sm">
      <button type="button" className="btn-secondary" onClick={() => setOpen(!open)} aria-expanded={open}>
        <FiGlobe /> Kündigungsfrist recherchieren
      </button>
      {open && <section aria-label="Öffentliche Webrecherche" className="mt-3 space-y-3 rounded-xl border border-white/10 p-4">
        <p className="text-sm leading-6 muted">
          Suche in öffentlichen AGB. Gib nur Anbieter, Tarif, Land und bei Bedarf das Vertragsjahr an.
          Dokumente, OCR-Text und Chatverlauf werden nicht angehängt. Auch Titel und Beschreibung
          werden wegen möglicher persönlicher Angaben nicht automatisch übernommen.
        </p>
        {status.isLoading && <p>Suchanbieter wird geladen …</p>}
        {status.isError && <p role="alert">Suchanbieter konnte nicht geladen werden.</p>}
        {status.data && !status.data.available && <p role="status" className="text-amber-200">{status.data.reason}</p>}
        <label className="block">
          <span className="mb-2 block">Öffentliche Suchanfrage</span>
          <input className="field" maxLength={300} value={query} disabled={busy}
            placeholder="Kündigungsfrist Magenta L Deutschland, Abschluss 2024"
            onChange={event => { setQuery(event.target.value); setConfirmed(false); setResult(null); }} />
        </label>
        <p className="text-xs muted">Genau dieser Text wird an {status.data?.provider || "den Suchanbieter"}
          {status.data?.model ? ` (${status.data.model})` : ""} übermittelt. Die Suche verursacht API-Kosten.</p>
        <label className="flex items-start gap-2 leading-5">
          <input type="checkbox" className="mt-1" checked={confirmed} disabled={busy}
            onChange={event => setConfirmed(event.target.checked)} />
          Die Suchanfrage enthält nur öffentliche Produktangaben, keine Namen, Kunden-/Vertragsnummern oder andere persönliche Daten.
        </label>
        <button type="button" className="btn-primary" onClick={() => void search()}
          disabled={busy || !confirmed || query.trim().length < 5 || !status.data?.available}>
          <FiSearch /> {busy ? "Recherche läuft …" : "Öffentlich suchen"}
        </button>
        {error && <p role="alert" className="text-red-300">{error}</p>}
        {result && <div role="status" className="space-y-3 border-t border-white/10 pt-3">
          <p className="text-xs muted">Gesucht: {result.query}</p>
          <p className="whitespace-pre-wrap break-words leading-6">{result.answer}</p>
          <ul className="space-y-2">
            {result.sources.map(source => <li key={source.url}>
              <a href={source.url} target="_blank" rel="noopener noreferrer" className="break-words text-[#77a7ff] underline">{source.title}</a>
            </li>)}
          </ul>
          <p className="text-amber-200">Öffentliche Bedingungen können vom individuellen Vertrag abweichen.
            Prüfe Tarif, Abschlussdatum und AGB-Version. Das Kündigungsfrist-Feld bleibt unverändert.</p>
        </div>}
      </section>}
    </div>
  );
}
