import { afterEach, expect, it, vi } from "vitest";
import { act, render, screen } from "../../test/utils";
import ReviewProgress from "./ReviewProgress";
import type { ReviewItem } from "./reviewTypes";

afterEach(() => vi.useRealTimers());

it("shows OCR progress without claiming a completed review", () => {
  const item: ReviewItem = { id: 1, title: "Synthetic", status: "pending", result: { progress: {
    stage: "waiting", completed_pages: 0, total_pages: 22, ocr_completed_pages: 4,
  } } };
  render(<ReviewProgress item={item} />);
  expect(screen.getByText(/4 von 22 PDF-Seiten gescannt/)).toBeInTheDocument();
  expect(screen.getByRole("progressbar")).toHaveAttribute("value", "4");
  expect(screen.queryByText(/vollständig geprüft/)).not.toBeInTheDocument();
});

it("distinguishes OCR completion from model waiting and warns when heartbeats stop", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-17T10:00:10Z"));
  const item: ReviewItem = { id: 1, title: "Synthetic", status: "processing", result: { progress: {
    stage: "analysis", stage_started_at: "2026-09-17T10:00:00Z", heartbeat_at: "2026-09-17T10:00:10Z",
    completed_pages: 0, total_pages: 6, ocr_completed_pages: 6, request_timeout_seconds: 300,
    files: [{ name: "main.pdf", pages: 4 }, { name: "support.pdf", pages: 2 }],
  } } };
  render(<ReviewProgress item={item} />);
  expect(screen.getByText(/6 von 6 PDF-Seiten gescannt/)).toBeInTheDocument();
  expect(screen.getByText(/Alle 6 Seiten gescannt. Eine gemeinsame KI-Auswertung/)).toBeInTheDocument();
  expect(screen.getByText(/seit 10 Sekunden/)).toBeInTheDocument();
  expect(screen.getByText(/Hauptdokument · main.pdf · 4 Seiten/)).toBeInTheDocument();
  expect(screen.getByText(/Anlage 1 · support.pdf · 2 Seiten/)).toBeInTheDocument();
  act(() => { vi.advanceTimersByTime(21000); });
  expect(screen.getByText(/Kein aktuelles Lebenszeichen/)).toBeInTheDocument();
});

it("shows a bounded rate-limit retry countdown while retaining OCR", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-17T10:00:00Z"));
  render(<ReviewProgress item={{ id: 1, title: "Synthetic", status: "processing", result: {
    reasoning_effort: "high", progress: { stage: "analysis", total_pages: 22, ocr_completed_pages: 22,
      retry_attempt: 2, retry_at: "2026-09-17T10:00:20Z" },
  } }} />);
  expect(screen.getByText(/Thinking: HIGH/)).toBeInTheDocument();
  expect(screen.getByText(/Versuch 2 in 20 Sekunden/)).toBeInTheDocument();
  act(() => { vi.advanceTimersByTime(5000); });
  expect(screen.getByText(/Versuch 2 in 15 Sekunden/)).toBeInTheDocument();
});
