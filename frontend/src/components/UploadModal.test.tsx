import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { fireEvent, render, screen, waitFor, within } from "../test/utils";
import type { Contract } from "../types";
import UploadModal from "./UploadModal";

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock("../api", () => ({ default: mocks }));
vi.mock("../App", () => ({ useUser: () => ({ user: { id: 1, default_workspace_id: 7 } }) }));

const pdf = (name: string) => new File(["%PDF-1.4\ntest"], name, { type: "application/pdf" });
const input = () => screen.getByLabelText("Dateien auswählen") as HTMLInputElement;
const upload = async (files: File[]) => {
  await userEvent.upload(input(), files);
  await waitFor(() => expect(within(screen.getByRole("list", { name: "Neue Dateien" })).getAllByRole("listitem").length).toBeGreaterThan(0));
};
const existing: Contract = {
  id: 12, title: "Bestehender Vertrag", version: 3,
  uploaded_at: "2026-09-17", file_extension: ".pdf", document_type: "contract",
  tags: [], is_protected: false, can_read: true, can_write: true, can_delete: true, can_manage_protection: true,
  attachments: [{ id: 41, filename: "Gespeicherte Anlage.pdf", size: 1200, uploaded_at: "2026-09-17" }],
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.get.mockResolvedValue({ data: [{ id: 7, name: "Workspace", can_write: true, is_default: true, owner_user_id: 1 }] });
  mocks.post.mockResolvedValue({ data: {} });
  mocks.put.mockResolvedValue({ data: {} });
});

describe("UploadModal", () => {
  it("keeps web research available while editing or clearing a saved notice period", async () => {
    mocks.get.mockImplementation(async (path) => ({ data: path === "/ai/notice-research"
      ? { available: true, provider: "mistral", model: "mistral-medium-latest" }
      : [{ id: 7, name: "Workspace", can_write: true, is_default: true, owner_user_id: 1 }] }));
    render(<UploadModal isOpen initialData={{ ...existing, title: "Magenta L", description: "Telekom Deutschland", notice_period: 3 }} onClose={vi.fn()} />);
    const period = screen.getByLabelText("Kündigungsfrist (Tage)");
    await waitFor(() => expect(period).toHaveValue("3"));
    await userEvent.click(screen.getByRole("button", { name: "Websuche zur Kündigungsfrist" }));
    expect(screen.getByRole("textbox", { name: "Öffentliche Suchanfrage" })).toHaveValue("Kündigungsfrist Magenta L – Telekom Deutschland");
    await userEvent.clear(period);
    expect(screen.getByRole("button", { name: "Websuche zur Kündigungsfrist" })).toBeVisible();
    expect(screen.getByRole("textbox", { name: "Öffentliche Suchanfrage" })).toHaveValue("Kündigungsfrist Magenta L – Telekom Deutschland");
    expect(mocks.post).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Änderungen speichern" }));
    await waitFor(() => expect(mocks.put).toHaveBeenCalledOnce());
    expect((mocks.put.mock.calls[0][1] as FormData).get("notice_period")).toBe("");
  });

  it("analyzes only the selected PDF and uploads all files in one contract", async () => {
    const close = vi.fn();
    const main = pdf("Hauptvertrag.pdf");
    const extra = pdf("Zusatzvereinbarung.pdf");
    const notes = new File(["Hinweise"], "Notizen.txt", { type: "text/plain" });
    mocks.post.mockImplementation(async (path) => ({ data: path === "/contracts/analyze" ? { title: "Aus der Zusatzvereinbarung" } : {} }));
    render(<UploadModal isOpen onClose={close} />);
    await upload([main, extra, notes]);
    const select = screen.getByRole("combobox", { name: "KI-Quelldatei" });
    expect(within(select).getAllByRole("option")).toHaveLength(2);
    await userEvent.selectOptions(select, "1");
    await userEvent.click(screen.getByRole("button", { name: "Mit KI automatisch ausfüllen" }));
    await waitFor(() => expect(screen.getByLabelText("Vertragstitel")).toHaveValue("Aus der Zusatzvereinbarung"));
    const analyzed = mocks.post.mock.calls[0][1] as FormData;
    expect(analyzed.get("file")).toBe(extra);
    expect(analyzed.getAll("attachments")).toEqual([]);
    await userEvent.click(screen.getByRole("button", { name: "Vertrag hochladen" }));
    await waitFor(() => expect(close).toHaveBeenCalledOnce());
    const saved = mocks.post.mock.calls[1][1] as FormData;
    expect(saved.get("file")).toBe(main);
    expect(saved.getAll("attachments")).toEqual([extra, notes]);
    expect(saved.get("list_id")).toBe("7");
    expect(saved.get("document_type")).toBe("contract");
    expect(mocks.post.mock.calls.map(([path]) => path)).toEqual(["/contracts/analyze", "/contracts"]);
  });

  it("adds files across selections, avoids duplicates and recovers the AI source after removal", async () => {
    render(<UploadModal isOpen onClose={vi.fn()} />);
    const first = pdf("Hauptvertrag.pdf");
    const second = pdf("Anhang.pdf");
    await upload([first]);
    await upload([first, second]);
    expect(within(screen.getByRole("list", { name: "Neue Dateien" })).getAllByRole("listitem")).toHaveLength(2);
    await userEvent.selectOptions(screen.getByLabelText("KI-Quelldatei"), "1");
    await userEvent.click(screen.getByRole("button", { name: "Anhang.pdf entfernen" }));
    expect(screen.queryByLabelText("KI-Quelldatei")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Mit KI automatisch ausfüllen" }));
    await waitFor(() => expect(mocks.post).toHaveBeenCalledOnce());
    expect((mocks.post.mock.calls[0][1] as FormData).get("file")).toBe(first);
  });

  it("keeps valid files when another file is rejected", async () => {
    render(<UploadModal isOpen onClose={vi.fn()} />);
    const main = pdf("Hauptvertrag.pdf");
    await upload([main]);
    const large = new File([new Uint8Array(10 * 1024 * 1024 + 1)], "Zu groß.pdf", { type: "application/pdf" });
    await userEvent.upload(input(), [large]);
    expect(await screen.findByRole("alert")).toHaveTextContent("maximal 10 MB pro Datei");
    expect(screen.getByRole("button", { name: "Hauptvertrag.pdf entfernen" })).toBeInTheDocument();
  });

  it("limits a contract to ten files and reports the remaining files", async () => {
    render(<UploadModal isOpen onClose={vi.fn()} />);
    await upload(Array.from({ length: 11 }, (_, index) => pdf(`Vertrag-${index}.pdf`)));
    expect(within(screen.getByRole("list", { name: "Neue Dateien" })).getAllByRole("listitem")).toHaveLength(10);
    expect(screen.getByRole("alert")).toHaveTextContent("Vertrag-10.pdf wurde nicht hinzugefügt");
  });

  it("adds attachments during editing without replacing the saved main document", async () => {
    const close = vi.fn();
    render(<UploadModal isOpen initialData={existing} onClose={close} />);
    const extra = pdf("Neue Anlage.pdf");
    await upload([extra]);
    await userEvent.click(screen.getByRole("button", { name: "Gespeicherte Anlage.pdf entfernen" }));
    await userEvent.click(screen.getByRole("button", { name: "Änderungen speichern" }));
    await waitFor(() => expect(close).toHaveBeenCalledOnce());
    const saved = mocks.put.mock.calls[0][1] as FormData;
    expect(saved.has("file")).toBe(false);
    expect(saved.getAll("attachments")).toEqual([extra]);
    expect(saved.getAll("removed_attachment_ids")).toEqual(["41"]);
    expect(saved.get("version")).toBe("3");
  });

  it("replaces the main document only when explicitly selected", async () => {
    render(<UploadModal isOpen initialData={existing} onClose={vi.fn()} />);
    const replacement = pdf("Neuer Hauptvertrag.pdf");
    await upload([replacement]);
    await userEvent.click(screen.getByRole("button", { name: "Als Hauptdokument verwenden" }));
    await userEvent.click(screen.getByRole("button", { name: "Änderungen speichern" }));
    await waitFor(() => expect(mocks.put).toHaveBeenCalledOnce());
    const saved = mocks.put.mock.calls[0][1] as FormData;
    expect(saved.get("file")).toBe(replacement);
    expect(saved.getAll("attachments")).toEqual([]);
  });

  it("directly replaces individual files even when all ten slots are occupied", async () => {
    const close = vi.fn();
    const fullDocument = {
      ...existing,
      attachments: Array.from({ length: 9 }, (_, index) => ({
        id: 41 + index, filename: `Anlage-${index}.pdf`, size: 1200, uploaded_at: "2026-09-17",
      })),
    };
    render(<UploadModal isOpen initialData={fullDocument} onClose={close} />);
    const main = pdf("Unterschriebener Vertrag.pdf");
    const attachment = pdf("Unterschriebene Anlage.pdf");
    expect(screen.getByRole("button", { name: "Hauptdokument ersetzen" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Anlage-3.pdf ersetzen" })).toBeEnabled();
    await userEvent.upload(screen.getByLabelText("Ersatzdatei für Hauptdokument auswählen"), main);
    await userEvent.upload(screen.getByLabelText("Ersatzdatei für Anlage-3.pdf auswählen"), attachment);
    expect(await screen.findAllByText(/Wird beim Speichern ersetzt/)).toHaveLength(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(mocks.put).not.toHaveBeenCalled();
    expect(mocks.post).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Änderungen speichern" }));
    await waitFor(() => expect(close).toHaveBeenCalledOnce());
    expect(mocks.put).toHaveBeenCalledOnce();
    expect(mocks.put.mock.calls[0][0]).toBe("/contracts/12");
    const saved = mocks.put.mock.calls[0][1] as FormData;
    expect(saved.get("file")).toBe(main);
    expect(saved.getAll("attachments")).toEqual([attachment]);
    expect(saved.getAll("removed_attachment_ids")).toEqual(["44"]);
    expect(saved.get("version")).toBe("3");
    expect(saved.get("title")).toBe(existing.title);
  });

  it("can discard replacements without promoting or removing unrelated new files", async () => {
    render(<UploadModal isOpen initialData={existing} onClose={vi.fn()} />);
    const extra = pdf("Zusätzliche Anlage.pdf");
    const replacement = pdf("Neuer Vertrag.pdf");
    await upload([extra, replacement]);
    const replacementRow = screen.getByRole("button", { name: "Neuer Vertrag.pdf entfernen" }).closest("li")!;
    await userEvent.click(within(replacementRow).getByRole("button", { name: "Als Hauptdokument verwenden" }));
    await userEvent.upload(screen.getByLabelText("Ersatzdatei für Gespeicherte Anlage.pdf auswählen"), pdf("Ersatzanlage.pdf"));
    await userEvent.click(screen.getByRole("button", { name: "Hauptdokument beibehalten" }));
    await userEvent.click(screen.getByRole("button", { name: "Gespeicherte Anlage.pdf beibehalten" }));
    expect(screen.queryByText(/Wird beim Speichern ersetzt/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Änderungen speichern" }));
    await waitFor(() => expect(mocks.put).toHaveBeenCalledOnce());
    const saved = mocks.put.mock.calls[0][1] as FormData;
    expect(saved.has("file")).toBe(false);
    expect(saved.getAll("attachments")).toEqual([extra]);
    expect(saved.getAll("removed_attachment_ids")).toEqual([]);
  });

  it.each([
    ["Hauptdokument", "file"],
    ["Gespeicherte Anlage.pdf", "attachments"],
  ])("keeps the last valid replacement for %s when another selection is invalid", async (name, field) => {
    render(<UploadModal isOpen initialData={existing} onClose={vi.fn()} />);
    const replacementInput = screen.getByLabelText(`Ersatzdatei für ${name} auswählen`);
    await userEvent.upload(replacementInput, pdf("Erste Auswahl.pdf"));
    const latest = pdf("Letzte Auswahl.pdf");
    await userEvent.upload(replacementInput, latest);
    const large = new File([new Uint8Array(10 * 1024 * 1024 + 1)], "Zu groß.pdf", { type: "application/pdf" });
    await userEvent.upload(replacementInput, large);
    expect(await screen.findByRole("alert")).toHaveTextContent("maximal 10 MB pro Datei");
    await userEvent.click(screen.getByRole("button", { name: "Änderungen speichern" }));
    await waitFor(() => expect(mocks.put).toHaveBeenCalledOnce());
    const saved = mocks.put.mock.calls[0][1] as FormData;
    expect(saved.getAll(field)).toEqual([latest]);
    expect(saved.getAll("removed_attachment_ids")).toEqual(field === "attachments" ? ["41"] : []);
  });

  it("removes only the selected attachment and discards its pending replacement", async () => {
    render(<UploadModal isOpen initialData={existing} onClose={vi.fn()} />);
    await userEvent.upload(screen.getByLabelText("Ersatzdatei für Gespeicherte Anlage.pdf auswählen"), pdf("Ersatz.pdf"));
    await userEvent.click(screen.getByRole("button", { name: "Gespeicherte Anlage.pdf entfernen" }));
    expect(screen.getByText("Wird beim Speichern entfernt")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mit KI automatisch ausfüllen" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Änderungen speichern" }));
    await waitFor(() => expect(mocks.put).toHaveBeenCalledOnce());
    const saved = mocks.put.mock.calls[0][1] as FormData;
    expect(saved.has("file")).toBe(false);
    expect(saved.getAll("attachments")).toEqual([]);
    expect(saved.getAll("removed_attachment_ids")).toEqual(["41"]);
  });

  it("allows a removal to be undone at capacity while another attachment is being replaced", async () => {
    const fullDocument = {
      ...existing,
      attachments: Array.from({ length: 9 }, (_, index) => ({
        id: 41 + index, filename: `Anlage-${index}.pdf`, size: 1200, uploaded_at: "2026-09-17",
      })),
    };
    render(<UploadModal isOpen initialData={fullDocument} onClose={vi.fn()} />);
    const replacement = pdf("Ersatz.pdf");
    await userEvent.upload(screen.getByLabelText("Ersatzdatei für Anlage-0.pdf auswählen"), replacement);
    await userEvent.click(screen.getByRole("button", { name: "Anlage-1.pdf entfernen" }));
    await upload([pdf("Extra.pdf")]);
    await userEvent.click(screen.getByRole("button", { name: "Anlage-1.pdf behalten" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Maximal 10 Dateien");
    await userEvent.click(screen.getByRole("button", { name: "Extra.pdf entfernen" }));
    await userEvent.click(screen.getByRole("button", { name: "Anlage-1.pdf behalten" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Änderungen speichern" }));
    await waitFor(() => expect(mocks.put).toHaveBeenCalledOnce());
    const saved = mocks.put.mock.calls[0][1] as FormData;
    expect(saved.getAll("attachments")).toEqual([replacement]);
    expect(saved.getAll("removed_attachment_ids")).toEqual(["41"]);
  });

  it("offers replacement PDFs for optional analysis and blocks replacement during analysis", async () => {
    let finish!: (value: { data: object }) => void;
    mocks.post.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    render(<UploadModal isOpen initialData={existing} onClose={vi.fn()} />);
    const main = pdf("Vertrag.pdf");
    const attachment = pdf("Anlage.pdf");
    await userEvent.upload(screen.getByLabelText("Ersatzdatei für Hauptdokument auswählen"), main);
    await userEvent.upload(screen.getByLabelText("Ersatzdatei für Gespeicherte Anlage.pdf auswählen"), attachment);
    const select = screen.getByLabelText("KI-Quelldatei");
    await userEvent.selectOptions(select, "1");
    await userEvent.click(screen.getByRole("button", { name: "Mit KI automatisch ausfüllen" }));
    await waitFor(() => expect(mocks.post).toHaveBeenCalledOnce());
    expect((mocks.post.mock.calls[0][1] as FormData).get("file")).toBe(attachment);
    expect(screen.getByRole("button", { name: "Hauptdokument ersetzen" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Gespeicherte Anlage.pdf ersetzen" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Hauptdokument beibehalten" })).toBeDisabled();
    finish({ data: {} });
    await waitFor(() => expect(screen.getByRole("button", { name: "Hauptdokument ersetzen" })).toBeEnabled());
  });

  it("discards pending replacements when editing is cancelled", async () => {
    const close = vi.fn();
    const view = render(<UploadModal isOpen initialData={existing} onClose={close} />);
    await userEvent.upload(screen.getByLabelText("Ersatzdatei für Hauptdokument auswählen"), pdf("Vertrag.pdf"));
    await userEvent.upload(screen.getByLabelText("Ersatzdatei für Gespeicherte Anlage.pdf auswählen"), pdf("Anlage.pdf"));
    await userEvent.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(close).toHaveBeenCalledOnce();
    expect(mocks.put).not.toHaveBeenCalled();
    view.rerender(<UploadModal isOpen={false} initialData={existing} onClose={close} />);
    view.rerender(<UploadModal isOpen initialData={existing} onClose={close} />);
    expect(screen.queryByText(/Wird beim Speichern ersetzt/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Änderungen speichern" }));
    await waitFor(() => expect(mocks.put).toHaveBeenCalledOnce());
    const saved = mocks.put.mock.calls[0][1] as FormData;
    expect(saved.has("file")).toBe(false);
    expect(saved.getAll("attachments")).toEqual([]);
    expect(saved.getAll("removed_attachment_ids")).toEqual([]);
  });

  it("blocks changes and closing during analysis", async () => {
    const close = vi.fn();
    let finish!: (value: { data: object }) => void;
    mocks.post.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    render(<UploadModal isOpen onClose={close} />);
    await upload([pdf("Vertrag.pdf"), pdf("Anhang.pdf")]);
    await userEvent.click(screen.getByRole("button", { name: "Mit KI automatisch ausfüllen" }));
    expect(screen.getByLabelText("KI-Quelldatei")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Vertrag.pdf entfernen" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Dialog schließen" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Vertrag hochladen" })).toBeDisabled();
    finish({ data: {} });
    await waitFor(() => expect(screen.getByRole("button", { name: "Dialog schließen" })).toBeEnabled());
    expect(close).not.toHaveBeenCalled();
  });

  it("clears pending files when the dialog reopens", async () => {
    const close = vi.fn();
    const view = render(<UploadModal isOpen onClose={close} />);
    await upload([pdf("Vertrag.pdf")]);
    view.rerender(<UploadModal isOpen={false} onClose={close} />);
    view.rerender(<UploadModal isOpen onClose={close} />);
    await waitFor(() => expect(screen.queryByRole("list", { name: "Neue Dateien" })).not.toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Vertragstitel"), { target: { value: "Titel" } });
    expect(screen.getByRole("button", { name: "Vertrag hochladen" })).toBeDisabled();
  });
});
