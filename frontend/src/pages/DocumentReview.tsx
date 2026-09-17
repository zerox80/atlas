import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FiCheckSquare, FiPause, FiPlay } from "react-icons/fi";
import api from "../api";
import { PageHeader } from "../components/ui";
import ReviewItemCard from "../features/documents/ReviewItemCard";
import type { ReviewPage, ReviewRun } from "../features/documents/reviewTypes";
import { reviewRequestError } from "../features/documents/reviewRequestError";
import { parseApiDate } from "../utils/apiDate";

export default function DocumentReview() {
  const client = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [controlling, setControlling] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const runs = useQuery(["document-reviews", "runs"], async () => (await api.get<ReviewRun[]>("/ai/reviews")).data,
    { refetchInterval: 3000 });
  const runId = selectedId || runs.data?.find(run => run.running)?.id || runs.data?.[0]?.id;
  const page = useQuery(["document-reviews", runId, offset], async () => (
    await api.get<ReviewPage>(`/ai/reviews/${runId}`, { params: { offset, limit: 50 } })
  ).data, { enabled: Boolean(runId), refetchInterval: 3000 });
  const running = Boolean(page.data?.running);
  const status = useQuery(["ai-status"], async () => (await api.get<{available: boolean; model?: string; external_document_processing?: boolean}>("/ai/status")).data);

  const control = async (id: string, action: "start" | "pause") => {
    setControlling(true);
    setError("");
    try {
      await api.post(`/ai/reviews/${id}/${action}`);
    } catch (err) {
      setError(reviewRequestError(err, "Prüfstatus konnte nicht geändert werden. Die Anzeige wird mit dem Server abgeglichen."));
    } finally {
      await client.invalidateQueries(["document-reviews"]);
      setControlling(false);
    }
  };
  const create = async () => {
    setCreating(true);
    setError("");
    try {
      const { data } = await api.post<ReviewRun>("/ai/reviews", { start: true });
      setSelectedId(data.id);
      setOffset(0);
      await client.invalidateQueries(["document-reviews"]);
    } catch (err) { setError(reviewRequestError(err, "Prüflauf konnte nicht angelegt werden.")); }
    finally { setCreating(false); }
  };
  const retry = async () => {
    if (!runId) return;
    try {
      await api.post(`/ai/reviews/${runId}/retry`);
      await control(runId, "start");
    } catch (err) { setError(reviewRequestError(err, "Erneuter Versuch fehlgeschlagen.")); }
  };
  const data = page.data;
  return <div className="app-page">
    <PageHeader eyebrow="Datenqualität" title="Alle Dokumente prüfen"
      description="Verträge und Rechnungen erneut mit dem aktuellen KI-Modell gegen die Originaldokumente abgleichen."
      actions={<button className="btn-primary" disabled={running || controlling || creating || !status.data?.available} onClick={() => void create()}>
        <FiCheckSquare /> {creating ? "Wird vorbereitet …" : "Alle Verträge & Rechnungen neu prüfen"}
    </button>} />
    <div className="surface mb-5 space-y-2 p-5 text-sm leading-6">
      <p>Korrekturen wählst du einzeln aus. Fehlende Angaben löschen keine gespeicherten Werte.
        Fertige Seitenabschnitte bleiben für die Fortsetzung gespeichert.</p>
      <details className="muted"><summary className="cursor-pointer">Umfang, API-Kosten und Ablauf · Modell {status.data?.model || "Nicht verfügbar"}</summary>
      <p className="mt-2">Prüft alle zugänglichen Dokumente in allen Workspaces, einschließlich geschützter Dokumente und PDF-Anlagen.
        Papierkorb und nicht unterstützte Dateiformate werden nicht analysiert.</p>
      <p>Die Prüfung nutzt die konfigurierte Dokument-KI und verursacht API-Kosten.</p>
      <p>Die Prüfung läuft auf dem Server weiter, auch nach Neuladen oder Schließen dieser Seite.
        Mit „Nach diesem Abschnitt pausieren“ hältst du sie an. Fertige Abschnitte bleiben gespeichert.
        Fehlerhafte Dokumente halten die übrige Prüfung nicht auf. Ein KI-Prüfergebnis kann Fehler enthalten.</p>
      </details>
    </div>
    {(error || page.data?.run_error || runs.isError || page.isError || status.isError) && <p role="alert" className="mb-5 text-[var(--danger)]">
      {error || page.data?.run_error || reviewRequestError(runs.error || page.error || status.error, "Prüfergebnisse oder KI-Status konnten nicht geladen werden.")}</p>}
    {status.data && !status.data.available && <p role="status" className="mb-5 text-[var(--warning)]">
      {status.data.external_document_processing === false ? "KI-Dokumentverarbeitung ist in der Backend-Konfiguration deaktiviert."
        : "KI-Prüfung nicht verfügbar. MISTRAL_API_KEY ist im Backend nicht konfiguriert."}</p>}
    {(runs.isLoading || (runId && page.isLoading)) && <p role="status" className="mb-5 muted">Prüfergebnisse werden geladen …</p>}
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
            · {data.counts.hints || 0} mit Hinweisen
            · {data.counts.error || 0} fehlgeschlagen · {data.counts.skipped || 0} nicht geprüft</p>
          <div className="flex flex-wrap gap-2">
            {running ? <button className="btn-secondary" disabled={controlling} onClick={() => void control(data.id, "pause")}><FiPause /> Nach diesem Abschnitt pausieren</button>
              : data.remaining > 0 && <button className="btn-primary" disabled={controlling || !status.data?.available} onClick={() => void control(data.id, "start")}><FiPlay /> Prüfung fortsetzen</button>}
            {!running && Boolean(data.counts.error) && <button className="btn-secondary" disabled={controlling || !status.data?.available} onClick={() => void retry()}>Fehler erneut versuchen</button>}
          </div>
        </div>
        {running && <p className="text-sm muted" role="status">Prüfung läuft auf dem Server · Diese Seite kann neu geladen oder geschlossen werden.</p>}
        {!running && data.remaining > 0 && <p className="text-sm muted" role="status">{data.counts.processing
          ? "Pause angefordert · Der laufende Abschnitt wird noch fertig geprüft."
          : "Prüfung pausiert · Fertige Abschnitte sind gespeichert."}</p>}
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
