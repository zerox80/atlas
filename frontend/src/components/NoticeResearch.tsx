import { useRef, useState } from "react";
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

const EXAMPLE_QUERY = "Kündigungsfrist Magenta L Deutschland, Abschluss 2024";

interface NoticeResearchProps {
  title?: string | null;
  description?: string | null;
}

function suggestQuery({ title, description }: NoticeResearchProps): string {
  const parts = [title, description].map(value => value?.replace(/\s+/g, " ").trim() || "");
  const context = parts.filter((part, index) => part && parts.indexOf(part) === index).join(" – ");
  if (!context) return "";
  const query = `Kündigungsfrist ${context}`;
  if (query.length <= 300) return query;
  const clipped = query.slice(0, 300);
  const boundary = clipped.lastIndexOf(" ");
  return boundary > 250 ? clipped.slice(0, boundary) : clipped;
}

/** Builds the editable suggestion locally; only the confirmed query is sent. */
export default function NoticeResearch(props: NoticeResearchProps) {
  const suggestion = suggestQuery(props);
  const inputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [queryOverride, setQueryOverride] = useState<string | null>(null);
  const query = queryOverride ?? suggestion;
  const [confirmedQuery, setConfirmedQuery] = useState<string | null>(null);
  const confirmed = confirmedQuery === query;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ResearchResult | null>(null);
  const status = useQuery(
    ["notice-research-status"],
    async () => (await api.get<{ available: boolean; provider: string; model: string; reason?: string }>("/ai/notice-research")).data,
    { enabled: open, staleTime: 60_000 },
  );
  const search = async () => {
    if (busy || !confirmed || query.trim().length < 5 || !status.data?.available) return;
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
        <FiGlobe /> Websuche zur Kündigungsfrist
      </button>
      {open && <section aria-label="Öffentliche Webrecherche" className="mt-3 space-y-3 rounded-xl border border-white/10 p-4">
        <p className="text-sm leading-6 muted">
          Suche in öffentlichen AGB. {suggestion && "Der Vorschlag stammt aus Titel und Beschreibung. "}
          Passe die Suchanfrage auf Anbieter, Tarif, Land und bei Bedarf das Vertragsjahr an.
        </p>
        {status.isLoading && <p>Suchanbieter wird geladen …</p>}
        {status.isError && <p role="alert">{getApiErrorMessage(status.error, "Suchanbieter konnte nicht geladen werden.")}</p>}
        {status.data && !status.data.available && <p role="status" className="text-amber-200">{status.data.reason}</p>}
        <label className="block">
          <span className="mb-2 block">Öffentliche Suchanfrage</span>
          <input ref={inputRef} className="field" maxLength={300} value={query} disabled={busy}
            placeholder={EXAMPLE_QUERY}
            onChange={event => { setQueryOverride(event.target.value); setConfirmedQuery(null); setResult(null); setError(""); }}
            onKeyDown={event => {
              if (event.key === "Enter") { event.preventDefault(); void search(); }
            }} />
        </label>
        {suggestion && query !== suggestion && <button type="button" className="btn-secondary" disabled={busy}
          onClick={() => {
            setQueryOverride(null); setConfirmedQuery(null); setResult(null); setError("");
            inputRef.current?.focus();
          }}>Vorschlag übernehmen</button>}
        {!suggestion && !query.trim() && <button type="button" className="btn-secondary" disabled={busy}
          onClick={() => {
            setQueryOverride(EXAMPLE_QUERY); setConfirmedQuery(null); setResult(null); setError("");
            inputRef.current?.focus();
          }}>Beispiel übernehmen</button>}
        <p className="text-xs muted">Genau dieser Text wird an {status.data?.provider || "den Suchanbieter"}
          {status.data?.model ? ` (${status.data.model})` : ""} übermittelt. Die Suche verursacht API-Kosten.</p>
        <label className="flex items-start gap-2 leading-5">
          <input type="checkbox" className="mt-1" checked={confirmed} disabled={busy}
            onChange={event => setConfirmedQuery(event.target.checked ? query : null)} />
          Die Suchanfrage enthält nur öffentliche Produktangaben, keine Namen, Kunden-/Vertragsnummern oder andere persönliche Daten.
        </label>
        <button type="button" className="btn-primary" onClick={() => void search()}
          disabled={busy || !confirmed || query.trim().length < 5 || !status.data?.available}>
          <FiSearch /> {busy ? "Recherche läuft …" : "Öffentlich suchen"}
        </button>
        {error && <p role="alert" className="text-red-300">{error}</p>}
        {result && result.query.trim().replace(/\s+/g, " ") === query.trim().replace(/\s+/g, " ") && <div role="status" className="space-y-3 border-t border-white/10 pt-3">
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
