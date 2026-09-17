import { beforeEach, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, screen, waitFor } from "../../test/utils";
import ReviewDocumentButton from "./ReviewDocumentButton";

const api = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("../../api", () => ({ default: api }));

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState({}, "", "/contracts");
  api.post.mockResolvedValue({ data: { id: "single-run", total: 1 } });
});

it("starts only the chosen document on click and opens its saved run", async () => {
  render(<ReviewDocumentButton documentId={23} />);
  expect(api.post).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Dieses Dokument mit KI prüfen" }));
  await waitFor(() => expect(api.post).toHaveBeenCalledExactlyOnceWith("/ai/reviews", { start: true, document_id: 23 }));
  await waitFor(() => expect(window.location.pathname + window.location.search).toBe("/reviews?run_id=single-run"));
});

it("does not start duplicate work while the request is pending", async () => {
  let resolve!: (value: unknown) => void;
  api.post.mockReturnValue(new Promise(done => { resolve = done; }));
  render(<ReviewDocumentButton documentId={23} retry />);
  await userEvent.click(screen.getByRole("button", { name: "Nur dieses Dokument erneut prüfen" }));
  expect(screen.getByRole("button", { name: "Prüfung wird gestartet …" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button"));
  expect(api.post).toHaveBeenCalledOnce();
  resolve({ data: { id: "single-run" } });
  await waitFor(() => expect(window.location.search).toBe("?run_id=single-run"));
});

it("shows an active-run conflict without starting a full review or navigating", async () => {
  api.post.mockRejectedValue({ isAxiosError: true, response: { status: 409, data: { detail: "Ein anderer Prüflauf ist noch aktiv." } } });
  render(<ReviewDocumentButton documentId={23} />);
  await userEvent.click(screen.getByRole("button"));
  expect(await screen.findByRole("alert")).toHaveTextContent("Ein anderer Prüflauf ist noch aktiv.");
  expect(screen.getByRole("button")).toBeEnabled();
  expect(window.location.pathname).toBe("/contracts");
  expect(api.post).toHaveBeenCalledOnce();
});

it("disables review for non-PDF main documents", () => {
  render(<ReviewDocumentButton documentId={23} isPdf={false} />);
  expect(screen.getByRole("button")).toBeDisabled();
  expect(api.post).not.toHaveBeenCalled();
});
