import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { FiCheckSquare } from "react-icons/fi";
import api from "../../api";
import { reviewRequestError } from "./reviewRequestError";
import type { ReviewRun } from "./reviewTypes";

export default function ReviewDocumentButton({ documentId, isPdf = true, retry = false }: {
  documentId: number; isPdf?: boolean; retry?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const client = useQueryClient();
  const navigate = useNavigate();
  const start = async () => {
    if (busy || !isPdf) return;
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post<ReviewRun>("/ai/reviews", { start: true, document_id: documentId });
      navigate(`/reviews?run_id=${encodeURIComponent(data.id)}`);
      await client.invalidateQueries(["document-reviews"]);
    } catch (err) {
      setError(reviewRequestError(err, "Einzelprüfung konnte nicht gestartet werden."));
    } finally {
      setBusy(false);
    }
  };
  return <div className="space-y-2">
    <button type="button" className="btn-secondary" disabled={busy || !isPdf} onClick={() => void start()}
      title={isPdf ? "Prüft nur dieses Dokument einschließlich seiner PDF-Anlagen. Es fallen API-Kosten an."
        : "Die KI-Prüfung unterstützt derzeit nur PDF-Hauptdokumente."}>
      <FiCheckSquare aria-hidden="true" />
      {busy ? "Prüfung wird gestartet …" : retry ? "Nur dieses Dokument erneut prüfen" : "Dieses Dokument mit KI prüfen"}
    </button>
    {error && <p role="alert" className="max-w-xl text-sm text-[var(--danger)]">{error}</p>}
  </div>;
}
