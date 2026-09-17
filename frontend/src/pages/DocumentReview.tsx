import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FiCheckSquare, FiPause, FiPlay } from "react-icons/fi";
import api from "../api";
import { PageHeader } from "../components/ui";
import ReviewItemCard from "../features/documents/ReviewItemCard";
import type { ReviewPage, ReviewRun } from "../features/documents/reviewTypes";
import { getApiErrorMessage } from "../utils/errorUtils";
import { parseApiDate } from "../utils/apiDate";

export default function DocumentReview() {
  const client = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [running, setRunning] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const active = useRef<string | null>(null);
  useEffect(() => () => { active.current = null; }, []);
  const runs = useQuery(["document-reviews", "runs"], async () => (await api.get<ReviewRun[]>("/ai/reviews")).data);
  const runId = selectedId || runs.data?.[0]?.id;
  const page = useQuery(["document-reviews", runId, offset], async () => (
    await api.get<ReviewPage>(`/ai/reviews/${runId}`, { params: { offset, limit: 50 } })
  ).data, { enabled: Boolean(runId), refetchInterval: running ? 5000 : false });
  const status = useQuery(["ai-status"], async () => (await api.get<{available: boolean; model?: string}>("/ai/status")).data);

  const execute = async (id: string) => {
    if (active.current) return;
    active.current = id;
    setRunning(true);
    setError("");
    try {
      while (active.current === id) {
        const started = Date.now();
        const response = await api.post<{finished: boolean}>(`/ai/reviews/${id}/next`, {}, { timeout: 0 });
        await client.invalidateQueries(["document-reviews"]);
        if (response.data.finished) break;
        // The server rate limit also applies when documents are skipped quickly.
        await new Promise(resolve => setTimeout(resolve, Math.max(0, 2200 - (Date.now() - started))));
      }
    } catch (err) {
      setError(getApiErrorMessage(err, "Prüfung unterbrochen. Gespeicherte Ergebnisse bleiben erhalten."));
    } finally {
      active.current = null;
      setRunning(false);
      await client.invalidateQueries(["document-reviews"]);
    }
  };
  const create = async () => {
    setCreating(true);
    setError("");
    try {
      const { data } = await api.post<ReviewRun>("/ai/reviews");
      setSelectedId(data.id);
      setOffset(0);
      await client.invalidateQueries(["document-reviews"]);
      void execute(data.id);
    } catch (err) { setError(getApiErrorMessage(err, "Prüflauf konnte nicht angelegt werden.")); }
    finally { setCreating(false); }
  };
  const retry = async () => {
    if (!runId) return;
    try {
      await api.post(`/ai/reviews/${runId}/retry`);
      void execute(runId);
    } catch (err) { setError(getApiErrorMessage(err, "Erneuter Versuch fehlgeschlagen.")); }
  };
  const data = page.data;
  return <div className="app-page">
    <PageHeader eyebrow="Datenqualität" title="Alle Dokumente prüfen"
      description="Verträge und Rechnungen erneut mit dem aktuellen KI-Modell gegen die Originaldokumente abgleichen."
      actions={<button className="btn-primary" disabled={running || creating || !status.data?.available} onClick={() => void create()}>
        <FiCheckSquare /> {creating ? "Wird vorbereitet …" : "Alle Verträge & Rechnungen neu prüfen"}
      </button>} />
    <div className="surface mb-5 space-y-2 p-5 text-sm leading-6">
      <p>Prüft alle zugänglichen Dokumente in allen Workspaces, einschließlich geschützter Dokumente und PDF-Anlagen.
        Papierkorb und nicht unterstützte Dateiformate werden nicht analysiert.</p>
      <p>Modell: <strong>{status.data?.model || "Nicht verfügbar"}</strong>. Die Prüfung nutzt die konfigurierte Dokument-KI und verursacht API-Kosten.
        Korrekturen wählst du einzeln aus. Unbelegte Kündigungsfristen werden als leer vorgeschlagen.</p>
      <p className="muted">Lass diese Seite für die Prüfung geöffnet. Beim Verlassen stoppt sie nach dem aktuellen Dokument;
        Ergebnisse werden gespeichert und der Lauf kann später fortgesetzt werden. Ein KI-Prüfergebnis kann Fehler enthalten.</p>
    </div>
    {(error || runs.isError || page.isError) && <p role="alert" className="mb-5 text-red-300">{error || "Prüfergebnisse konnten nicht geladen werden."}</p>}
    {Boolean(runs.data?.length) && <label className="mb-5 block max-w-xl">
      <span className="mb-2 block text-sm">Gespeicherter Prüflauf</span>
      <select className="field" value={runId} disabled={running || creating} onChange={event => { setSelectedId(event.target.value); setOffset(0); }}>
        {runs.data!.map(run => <option key={run.id} value={run.id}>
          {parseApiDate(run.created_at).toLocaleString("de-DE")} · {run.model} · {run.total - run.remaining}/{run.total}
        </option>)}
      </select>
    </label>}
    {data && <>
      <section className="surface mb-5 space-y-4 p-5" aria-label="Prüffortschritt">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p role="status">{data.total - data.remaining} von {data.total} bearbeitet · {data.counts.issues || 0} mit Prüfbedarf
            · {data.counts.error || 0} fehlgeschlagen · {data.counts.skipped || 0} nicht geprüft</p>
          <div className="flex flex-wrap gap-2">
            {running ? <button className="btn-secondary" onClick={() => { active.current = null; }}><FiPause /> Nach diesem Dokument pausieren</button>
              : data.remaining > 0 && <button className="btn-primary" disabled={!status.data?.available} onClick={() => void execute(data.id)}><FiPlay /> Prüfung fortsetzen</button>}
            {!running && Boolean(data.counts.error) && <button className="btn-secondary" onClick={() => void retry()}>Fehler erneut versuchen</button>}
          </div>
        </div>
        <progress className="h-2 w-full accent-[#b8f15a]" value={data.total - data.remaining} max={data.total || 1} aria-label="Bearbeitete Dokumente" />
        {!data.total && <p>Keine zugänglichen Dokumente vorhanden.</p>}
      </section>
      <div className="space-y-4">{data.items.map(item => <ReviewItemCard key={`${data.id}-${item.id}`} item={item} runId={data.id} />)}</div>
      {data.total > 50 && <nav aria-label="Prüfergebnisse Seiten" className="mt-5 flex items-center gap-3">
        <button className="btn-secondary" disabled={!offset} onClick={() => setOffset(offset - 50)}>Zurück</button>
        <span>{offset + 1}–{Math.min(offset + 50, data.total)} von {data.total}</span>
        <button className="btn-secondary" disabled={offset + 50 >= data.total} onClick={() => setOffset(offset + 50)}>Weiter</button>
      </nav>}
    </>}
  </div>;
}
