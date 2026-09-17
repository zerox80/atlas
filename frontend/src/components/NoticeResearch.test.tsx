import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, screen, waitFor } from "../test/utils";
import NoticeResearch from "./NoticeResearch";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("../api", () => ({ default: api }));

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockResolvedValue({ data: { available: true, provider: "mistral", model: "mistral-medium-latest" } });
  api.post.mockImplementation(async (_path, body) => ({ data: {
    query: body.query, answer: "Bitte die AGB-Version vergleichen.",
    sources: [{ title: "Anbieter-AGB", url: "https://example.com/agb" }], provider: "mistral", model: "mistral-medium-latest",
  } }));
});

describe("NoticeResearch", () => {
  it("prefills a local title and description suggestion and sends only the confirmed edited text", async () => {
    render(<NoticeResearch title="Magenta L" description="Telekom Deutschland, Abschluss 2024" />);
    expect(api.get).not.toHaveBeenCalled();
    expect(api.post).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Websuche zur Kündigungsfrist" }));
    const input = screen.getByRole("textbox", { name: "Öffentliche Suchanfrage" });
    expect(input).toHaveValue("Kündigungsfrist Magenta L – Telekom Deutschland, Abschluss 2024");
    expect(screen.getByRole("button", { name: "Öffentlich suchen" })).toBeDisabled();
    await userEvent.clear(input);
    await userEvent.type(input, "Kündigungsfrist Magenta L Deutschland 2024");
    expect(api.post).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Öffentlich suchen" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledOnce());
    expect(api.post.mock.calls[0][1]).toEqual({ query: "Kündigungsfrist Magenta L Deutschland 2024", confirmed_public: true });
  });

  it("updates automatic suggestions without reusing confirmation or overwriting manual edits", async () => {
    const { rerender } = render(<NoticeResearch title="Magenta L" />);
    await userEvent.click(screen.getByRole("button", { name: "Websuche zur Kündigungsfrist" }));
    const input = screen.getByRole("textbox");
    await userEvent.click(screen.getByRole("checkbox"));
    rerender(<NoticeResearch title="Magenta XL" description="Abschluss 2024" />);
    expect(input).toHaveValue("Kündigungsfrist Magenta XL – Abschluss 2024");
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    await userEvent.clear(input);
    await userEvent.type(input, "Mein angepasster Suchtext");
    rerender(<NoticeResearch title="Magenta S" />);
    expect(input).toHaveValue("Mein angepasster Suchtext");
    await userEvent.click(screen.getByRole("button", { name: "Vorschlag übernehmen" }));
    expect(input).toHaveValue("Kündigungsfrist Magenta S");
    expect(input).toHaveFocus();
    expect(api.post).not.toHaveBeenCalled();
  });

  it("limits long document descriptions to the supported search length", async () => {
    render(<NoticeResearch title="Magenta L" description={"Öffentliche Tarifbeschreibung ".repeat(50)} />);
    await userEvent.click(screen.getByRole("button", { name: "Websuche zur Kündigungsfrist" }));
    const query = (screen.getByRole("textbox") as HTMLInputElement).value;
    expect(query).toContain("Kündigungsfrist Magenta L");
    expect(query.length).toBeLessThanOrEqual(300);
    expect(api.post).not.toHaveBeenCalled();
  });

  it("lets the user take over the placeholder as an editable query without starting a search", async () => {
    render(<NoticeResearch />);
    await userEvent.click(screen.getByRole("button", { name: "Websuche zur Kündigungsfrist" }));
    const input = screen.getByRole("textbox", { name: "Öffentliche Suchanfrage" });
    const example = input.getAttribute("placeholder");
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Beispiel übernehmen" }));
    expect(input).toHaveValue(example);
    expect(input).toHaveFocus();
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(api.post).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Öffentlich suchen" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledOnce());
    expect(api.post.mock.calls[0][1]).toEqual({ query: example, confirmed_public: true });
  });

  it("uses Enter for research without submitting the surrounding document form", async () => {
    const saveDocument = vi.fn(event => event.preventDefault());
    render(<form onSubmit={saveDocument}><NoticeResearch /><button type="submit">Speichern</button></form>);
    await userEvent.click(screen.getByRole("button", { name: "Websuche zur Kündigungsfrist" }));
    const input = screen.getByRole("textbox");
    await userEvent.type(input, "Magenta L{Enter}");
    expect(api.post).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.type(input, "{Enter}");
    await waitFor(() => expect(api.post).toHaveBeenCalledOnce());
    expect(saveDocument).not.toHaveBeenCalled();
  });

  it("sends only manually entered public text after confirmation and resets consent when edited", async () => {
    render(<NoticeResearch />);
    expect(api.get).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Websuche zur Kündigungsfrist" }));
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
    await userEvent.click(screen.getByRole("button", { name: "Websuche zur Kündigungsfrist" }));
    expect(await screen.findByText("Recherche ist nicht konfiguriert.")).toBeInTheDocument();
    await userEvent.type(screen.getByRole("textbox"), "Magenta L");
    await userEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("button", { name: "Öffentlich suchen" })).toBeDisabled();
    expect(api.post).not.toHaveBeenCalled();
  });

  it("shows the specific provider failure and lets the user retry explicitly", async () => {
    api.post.mockRejectedValueOnce({ response: { status: 502, data: {
      detail: "Mistral meldet ein Anfrage- oder Kontingentlimit (HTTP 429). Die Kündigungsfrist bleibt unverändert.",
    } } });
    render(<NoticeResearch />);
    await userEvent.click(screen.getByRole("button", { name: "Websuche zur Kündigungsfrist" }));
    await userEvent.type(screen.getByRole("textbox"), "Magenta L");
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Öffentlich suchen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Mistral meldet ein Anfrage- oder Kontingentlimit (HTTP 429)");
    expect(api.post).toHaveBeenCalledOnce();
    await userEvent.click(screen.getByRole("button", { name: "Öffentlich suchen" }));
    expect(await screen.findByRole("link", { name: "Anbieter-AGB" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
