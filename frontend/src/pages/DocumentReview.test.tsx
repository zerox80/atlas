import { afterEach, beforeEach, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { act, render, screen, waitFor } from "../test/utils";
import DocumentReview from "./DocumentReview";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("../api", () => ({ default: api }));

const run = { id: "saved-run", model: "zai-glm-latest", created_at: "2026-09-17T09:00:00Z", total: 2, remaining: 1, counts: { issues: 1, pending: 1 } };
afterEach(() => vi.useRealTimers());
beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockImplementation(async (url: string) => ({ data:
    url === "/ai/status" ? { available: true, model: "zai-glm-latest" } :
    url === "/ai/reviews" ? [run] : { ...run, items: [] },
  }));
});

it("loads a saved run without paid work and resumes only on demand", async () => {
  api.post.mockResolvedValue({ data: { finished: true } });
  render(<DocumentReview />);
  expect(await screen.findByText(/1 von 2 bearbeitet/)).toBeInTheDocument();
  expect(api.post).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Prüfung fortsetzen" }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("/ai/reviews/saved-run/next", {}, { timeout: 30000 }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Prüfung fortsetzen" })).toBeEnabled());
  expect(api.post).toHaveBeenCalledOnce();
});

it("keeps a busy background job running and stops scheduling after pause", async () => {
  let complete!: (value: { data: { finished: boolean; busy: boolean; retry_after_ms: number } }) => void;
  api.post.mockReturnValue(new Promise(resolve => { complete = resolve; }));
  render(<DocumentReview />);
  await userEvent.click(await screen.findByRole("button", { name: "Prüfung fortsetzen" }));
  await waitFor(() => expect(api.post).toHaveBeenCalledOnce());
  await userEvent.click(screen.getByRole("button", { name: "Nach diesem Abschnitt pausieren" }));
  await act(async () => { complete({ data: { finished: false, busy: true, retry_after_ms: 3000 } }); });
  await waitFor(() => expect(screen.getByRole("button", { name: "Prüfung fortsetzen" })).toBeEnabled());
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(api.post).toHaveBeenCalledOnce();
});

it("displays the HTTP code and server reason when scheduling fails", async () => {
  api.post.mockRejectedValue({ isAxiosError: true, response: { status: 409, data: { detail: "Das Analysemodell wurde geändert. Bitte einen neuen Prüflauf starten." } } });
  render(<DocumentReview />);
  await userEvent.click(await screen.findByRole("button", { name: "Prüfung fortsetzen" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("HTTP 409: Das Analysemodell wurde geändert.");
  expect(screen.getByRole("button", { name: "Prüfung fortsetzen" })).toBeEnabled();
});

it("does not start another document after leaving the page during a request", async () => {
  let complete!: (value: { data: { finished: boolean } }) => void;
  api.post.mockReturnValue(new Promise(resolve => { complete = resolve; }));
  const page = render(<DocumentReview />);
  await userEvent.click(await screen.findByRole("button", { name: "Prüfung fortsetzen" }));
  await waitFor(() => expect(api.post).toHaveBeenCalledOnce());
  vi.useFakeTimers();
  page.unmount();
  await act(async () => {
    complete({ data: { finished: false } });
    await vi.runAllTimersAsync();
  });
  expect(api.post).toHaveBeenCalledOnce();
});
