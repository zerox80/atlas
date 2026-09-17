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
