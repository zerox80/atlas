import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, screen, waitFor } from "../test/utils";
import NoticeResearch from "./NoticeResearch";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("../api", () => ({ default: api }));

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockResolvedValue({ data: { available: true, provider: "mistral", model: "mistral-medium-latest" } });
  api.post.mockResolvedValue({ data: {
    query: "Kündigungsfrist Magenta L Deutschland 2024", answer: "Bitte die AGB-Version vergleichen.",
    sources: [{ title: "Anbieter-AGB", url: "https://example.com/agb" }], provider: "mistral", model: "mistral-medium-latest",
  } });
});

describe("NoticeResearch", () => {
  it("sends only manually entered public text after confirmation and resets consent when edited", async () => {
    render(<NoticeResearch />);
    expect(api.get).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Kündigungsfrist recherchieren" }));
    const input = screen.getByRole("textbox", { name: "Öffentliche Suchanfrage" });
    const submit = screen.getByRole("button", { name: "Öffentlich suchen" });
    expect(input).toHaveValue("");
    await userEvent.type(input, "Kündigungsfrist Magenta L Deutschland 2024");
    expect(submit).toBeDisabled();
    expect(api.post).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(submit);
    await waitFor(() => expect(api.post).toHaveBeenCalledOnce());
    expect(api.post.mock.calls[0].slice(0, 2)).toEqual(["/ai/notice-research", {
      query: "Kündigungsfrist Magenta L Deutschland 2024", confirmed_public: true,
    }]);
    expect(await screen.findByRole("link", { name: "Anbieter-AGB" })).toHaveAttribute("href", "https://example.com/agb");
    expect(screen.getByText(/Das Kündigungsfrist-Feld bleibt unverändert/)).toBeInTheDocument();
    await userEvent.type(input, " Telekom");
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(submit).toBeDisabled();
    expect(screen.queryByRole("link", { name: "Anbieter-AGB" })).not.toBeInTheDocument();
  });

  it("keeps searching disabled when the separate provider is unavailable", async () => {
    api.get.mockResolvedValue({ data: { available: false, reason: "Recherche ist nicht konfiguriert." } });
    render(<NoticeResearch />);
    await userEvent.click(screen.getByRole("button", { name: "Kündigungsfrist recherchieren" }));
    expect(await screen.findByText("Recherche ist nicht konfiguriert.")).toBeInTheDocument();
    await userEvent.type(screen.getByRole("textbox"), "Magenta L");
    await userEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("button", { name: "Öffentlich suchen" })).toBeDisabled();
    expect(api.post).not.toHaveBeenCalled();
  });
});
