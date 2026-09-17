import { afterEach, expect, it, vi } from "vitest";
import { act, render, screen } from "../../test/utils";
import ReviewProgress from "./ReviewProgress";
import type { ReviewItem } from "./reviewTypes";

afterEach(() => vi.useRealTimers());

it("distinguishes OCR completion from model waiting and warns when heartbeats stop", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-17T10:00:10Z"));
  const item: ReviewItem = { id: 1, title: "Synthetic", status: "processing", result: { progress: {
    stage: "analysis", stage_started_at: "2026-09-17T10:00:00Z", heartbeat_at: "2026-09-17T10:00:10Z",
    completed_pages: 0, total_pages: 6, ocr_completed_pages: 4, request_timeout_seconds: 300,
    files: [{ name: "main.pdf", pages: 4 }, { name: "support.pdf", pages: 2 }],
  } } };
  render(<ReviewProgress item={item} />);
  expect(screen.getByText(/0 von 6 PDF-Seiten fertig geprüft/)).toBeInTheDocument();
  expect(screen.getByText(/Texterkennung abgeschlossen \(4 Seiten\)/)).toBeInTheDocument();
  expect(screen.getByText(/seit 10 Sekunden/)).toBeInTheDocument();
  expect(screen.getByText(/Hauptdokument · main.pdf · 4 Seiten/)).toBeInTheDocument();
  expect(screen.getByText(/Anlage 1 · support.pdf · 2 Seiten/)).toBeInTheDocument();
  act(() => { vi.advanceTimersByTime(21000); });
  expect(screen.getByText(/Kein aktuelles Lebenszeichen/)).toBeInTheDocument();
});
