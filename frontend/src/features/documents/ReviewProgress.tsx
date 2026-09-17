import { useEffect, useState } from "react";
import type { ReviewItem } from "./reviewTypes";
import { stageLabels } from "./reviewPresentation";
import { parseApiDate } from "../../utils/apiDate";

export default function ReviewProgress({ item }: { item: ReviewItem }) {
  const progress = item.result?.progress;
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (item.status !== "processing") return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [item.status]);
  if (!progress) return null;
  const elapsed = progress.stage_started_at ? Math.max(0, Math.floor((now - parseApiDate(progress.stage_started_at).getTime()) / 1000)) : null;
  const stale = progress.heartbeat_at && now - parseApiDate(progress.heartbeat_at).getTime() > 20000;
  return <div className="mt-3 break-words text-sm muted">
    {progress.retry_message && progress.stage !== "complete" && <p className="text-[var(--warning)]">{progress.retry_message}</p>}
    {progress.total_pages != null && <p>{progress.completed_pages || 0} von {progress.total_pages} PDF-Seiten fertig geprüft
      {progress.total_sections != null && ` · ${progress.completed_sections || 0}/${progress.total_sections} Seitenpakete`}</p>}
    {progress.files && <details className="mt-1"><summary className="cursor-pointer">
      Seitenumfang: {progress.files.length} PDF-Datei(en), einschließlich PDF-Anlagen</summary>
      <ul>{progress.files.map((file, index) => <li key={index}>{index === 0 ? "Hauptdokument" : `Anlage ${index}`} · {file.name} · {file.pages} Seiten</li>)}</ul>
    </details>}
    {progress.total_pages != null && progress.stage !== "complete" && <progress
      className="my-2 h-1.5 w-full accent-[var(--accent)]" value={progress.completed_pages || 0} max={progress.total_pages || 1}
      aria-label={`Fertig geprüfte Seiten: ${item.title}`} />}
    {progress.document_name && progress.stage !== "complete" && <p>{progress.document_name} · Seiten {progress.first_page}–{progress.last_page}
      {progress.stage && ` · ${stageLabels[progress.stage] || progress.stage}`}</p>}
    {item.status === "processing" && <div role="status" className="mt-2 space-y-1">
      {(progress.stage === "analysis" || progress.stage === "analysis_retry") && <p>Texterkennung abgeschlossen{progress.ocr_completed_pages != null && ` (${progress.ocr_completed_pages} Seiten)`}.
        Warte auf die KI-Auswertung dieses Seitenpakets. Der Prüfstand steigt nach Eingang und Prüfung der Antwort.</p>}
      <p>{progress.stage && (stageLabels[progress.stage] || progress.stage)}{elapsed != null && ` · seit ${elapsed} Sekunden`}
        {progress.request_timeout_seconds != null && ` · Zeitlimit je OCR-/KI-Anfrage: ${progress.request_timeout_seconds} Sekunden`}</p>
      {progress.heartbeat_at && <p className={stale ? "text-[var(--warning)]" : ""}>{stale
        ? "Kein aktuelles Lebenszeichen empfangen. Verbindung oder Serververarbeitung prüfen."
        : "Serververarbeitung aktiv · Lebenszeichen wird regelmäßig aktualisiert."}</p>}
    </div>}
  </div>;
}
