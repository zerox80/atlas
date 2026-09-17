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
  const scanned = progress.ocr_completed_pages || 0;
  const retrySeconds = progress.retry_at ? Math.max(0, Math.ceil((parseApiDate(progress.retry_at).getTime() - now) / 1000)) : null;
  return <div className="mt-3 break-words text-sm muted">
    {progress.total_pages != null && <p>{progress.stage === "complete"
      ? `${progress.total_pages} PDF-Seiten vollständig geprüft`
      : `${scanned} von ${progress.total_pages} PDF-Seiten gescannt`}</p>}
    {progress.files && <details className="mt-1"><summary className="cursor-pointer">
      Seitenumfang: {progress.files.length} PDF-Datei(en), einschließlich PDF-Anlagen</summary>
      <ul>{progress.files.map((file, index) => <li key={index}>{index === 0 ? "Hauptdokument" : `Anlage ${index}`} · {file.name} · {file.pages} Seiten</li>)}</ul>
    </details>}
    {progress.total_pages != null && progress.stage !== "complete" && <progress
      className="my-2 h-1.5 w-full accent-[var(--accent)]" value={scanned} max={progress.total_pages || 1}
      aria-label={`Gescannte Seiten: ${item.title}`} />}
    {progress.stage === "analysis_pending" && <p>Alle Seiten gescannt · Eine gemeinsame KI-Auswertung steht aus.</p>}
    {progress.document_name && progress.stage === "ocr" && <p>{progress.document_name} · Seiten {progress.first_page}–{progress.last_page}
      {progress.stage && ` · ${stageLabels[progress.stage] || progress.stage}`}</p>}
    {item.status === "processing" && <div role="status" className="mt-2 space-y-1">
      {progress.stage === "analysis" && <p>Alle {scanned} Seiten gescannt. Eine gemeinsame KI-Auswertung des gesamten Dokuments einschließlich PDF-Anlagen läuft.
        {item.result?.reasoning_effort && ` Thinking: ${item.result.reasoning_effort.toUpperCase()}.`}</p>}
      {retrySeconds != null && <p className="text-[var(--warning)]">API-Rate-Limit · Versuch {progress.retry_attempt} in {retrySeconds} Sekunden. Gescannte Seiten bleiben gespeichert.</p>}
      <p>{progress.stage && (stageLabels[progress.stage] || progress.stage)}{elapsed != null && ` · seit ${elapsed} Sekunden`}
        {progress.request_timeout_seconds != null && ` · Zeitlimit je OCR-/KI-Anfrage: ${progress.request_timeout_seconds} Sekunden`}</p>
      {progress.heartbeat_at && <p className={stale ? "text-[var(--warning)]" : ""}>{stale
        ? "Kein aktuelles Lebenszeichen empfangen. Verbindung oder Serververarbeitung prüfen."
        : "Atlas-Server aktiv · Das Lebenszeichen bestätigt keinen Fortschritt beim KI-Anbieter."}</p>}
    </div>}
  </div>;
}
