import { beforeEach, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, screen, waitFor } from "../test/utils";
import DocumentReview from "./DocumentReview";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("../api", () => ({ default: api }));
const run = { id: "saved-run", model: "zai-glm-latest", created_at: "2026-09-17T09:00:00Z", total: 2, remaining: 1, counts: { issues: 1, pending: 1 } };
let running = false;
beforeEach(() => {
  vi.clearAllMocks();
  running = false;
  api.get.mockImplementation(async (url: string) => ({ data:
    url === "/ai/status" ? { available: true, model: "zai-glm-latest" } :
    url === "/ai/reviews" ? [{ ...run, running }] : { ...run, running, items: [] },
  }));
  api.post.mockImplementation(async (url: string) => {
    running = url.endsWith("/start");
    return { data: { ...run, running } };
  });
});

it("loads a paused run without paid work and starts server execution only on demand", async () => {
  render(<DocumentReview />);
  expect(await screen.findByText(/1 von 2 bearbeitet/)).toBeInTheDocument();
  expect(api.post).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Prüfung fortsetzen" }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("/ai/reviews/saved-run/start"));
  expect(await screen.findByRole("button", { name: "Nach diesem Abschnitt pausieren" })).toBeEnabled();
  expect(api.post).toHaveBeenCalledOnce();
});

it("restores a running review after reload without scheduling another job", async () => {
  running = true;
  const page = render(<DocumentReview />);
  expect(await screen.findByRole("button", { name: "Nach diesem Abschnitt pausieren" })).toBeEnabled();
  expect(screen.queryByRole("button", { name: "Prüfung fortsetzen" })).not.toBeInTheDocument();
  page.unmount();
  render(<DocumentReview />);
  expect(await screen.findByRole("button", { name: "Nach diesem Abschnitt pausieren" })).toBeEnabled();
  expect(screen.getByText(/^Prüfung läuft auf dem Server ·/)).toBeInTheDocument();
  expect(api.post).not.toHaveBeenCalled();
});

it("persists an explicit pause on the server", async () => {
  running = true;
  render(<DocumentReview />);
  await userEvent.click(await screen.findByRole("button", { name: "Nach diesem Abschnitt pausieren" }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("/ai/reviews/saved-run/pause"));
  expect(await screen.findByRole("button", { name: "Prüfung fortsetzen" })).toBeEnabled();
  expect(api.post).toHaveBeenCalledOnce();
});

it("displays the HTTP code and server reason when starting fails", async () => {
  api.post.mockRejectedValue({ isAxiosError: true, response: { status: 409, data: { detail: "Das Analysemodell wurde geändert. Bitte einen neuen Prüflauf starten." } } });
  render(<DocumentReview />);
  await userEvent.click(await screen.findByRole("button", { name: "Prüfung fortsetzen" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("HTTP 409: Das Analysemodell wurde geändert.");
  await waitFor(() => expect(screen.getByRole("button", { name: "Prüfung fortsetzen" })).toBeEnabled());
});
