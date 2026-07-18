import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "../test/utils";
import AdminPanel from "./AdminPanel";

const { mockGet, mockPost, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockDelete: vi.fn(),
}));

vi.mock("../api", () => ({
  default: {
    get: mockGet,
    post: mockPost,
    put: vi.fn(),
    delete: mockDelete,
  },
  fetchContractPage: async () => ({
    items: [],
    summary: {
      all: 0,
      active: 0,
      attention: 0,
      expired: 0,
      total_value: 0,
      current_month_value: 0,
    },
    has_more: false,
    next_cursor_uploaded_at: null,
    next_cursor_id: null,
  }),
}));

const users = [
  {
    id: 2,
    username: "alice",
    role: "user",
    is_active: true,
    created_at: "2026-07-16T10:00:00Z",
    has_2fa: false,
  },
];

describe("AdminPanel user deletion", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockDelete.mockReset();
    mockGet.mockImplementation((url: string) => {
      if (url === "/admin/users") return Promise.resolve({ data: users });
      return Promise.resolve({ data: [] });
    });
    mockPost.mockResolvedValue({ data: undefined });
    mockDelete.mockResolvedValue({ data: undefined });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("permanently deletes a user after confirmation", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<AdminPanel />);

    await screen.findByText("alice");
    fireEvent.click(screen.getByTitle("Dauerhaft löschen"));

    expect(confirmSpy).toHaveBeenCalledWith(
      "Benutzer „alice“ wirklich dauerhaft löschen? Dieser Vorgang kann nicht rückgängig gemacht werden.",
    );
    expect(mockDelete).toHaveBeenCalledWith("/admin/users/2");
  });

  it("does not delete a user when confirmation is cancelled", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<AdminPanel />);

    await screen.findByText("alice");
    fireEvent.click(screen.getByTitle("Dauerhaft löschen"));

    expect(mockDelete).not.toHaveBeenCalled();
  });
});

describe("AdminPanel document backup", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockDelete.mockReset();
    mockGet.mockImplementation((url: string) => {
      if (url === "/admin/users") return Promise.resolve({ data: users });
      return Promise.resolve({ data: [] });
    });
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: vi.fn(() => "blob:atlas-backup"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: vi.fn(),
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const openBackupTab = async () => {
    render(<AdminPanel />);
    await screen.findByText("alice");
    fireEvent.click(screen.getByRole("button", { name: "Datensicherung" }));
    return screen.getByRole("button", { name: "Alles sichern" });
  };

  it("shows the backup tab and cancels without starting a request", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    const backupButton = await openBackupTab();

    expect(
      screen.getByText("Verträge und Rechnungen sichern"),
    ).toBeInTheDocument();
    expect(screen.getByText(/nicht passwortgeschützt/i)).toBeInTheDocument();
    fireEvent.click(backupButton);

    expect(confirmSpy).toHaveBeenCalledWith(
      [
        "Diese Datensicherung enthält alle Verträge und Rechnungen",
        "einschließlich geschützter Dokumente. Die ZIP ist nicht",
        "passwortgeschützt. Jetzt erstellen?",
      ].join(" "),
    );
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("downloads the blob, shows progress and releases the object URL", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    let resolveBackup!: (value: unknown) => void;
    mockPost.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveBackup = resolve;
      }),
    );
    let downloadedFilename = "";
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        downloadedFilename = this.download;
      });
    const backupButton = await openBackupTab();

    fireEvent.click(backupButton);

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/admin/backup", undefined, {
        responseType: "blob",
      });
    });
    const runningButton = screen.getByRole("button", {
      name: "Sicherung wird erstellt …",
    });
    expect(runningButton).toBeDisabled();
    expect(runningButton).toHaveAttribute("aria-busy", "true");

    await act(async () => {
      resolveBackup({
        data: new Blob(["zip-content"], { type: "application/zip" }),
        headers: {
          "content-disposition":
            'attachment; filename="atlas-datensicherung-2026-07-17_12-30-00Z.zip"',
        },
      });
      await Promise.resolve();
    });

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Alles sichern" }),
      ).toBeEnabled(),
    );
    expect(URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(clickSpy).toHaveBeenCalledOnce();
    expect(downloadedFilename).toBe(
      "atlas-datensicherung-2026-07-17_12-30-00Z.zip",
    );
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:atlas-backup");
    expect(document.querySelector("a[download]")).not.toBeInTheDocument();
  });

  it("shows a clear server error and enables retrying", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mockPost.mockRejectedValueOnce({
      response: {
        data: { detail: "Datensicherung ist vorübergehend nicht verfügbar" },
      },
    });
    const backupButton = await openBackupTab();

    fireEvent.click(backupButton);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Datensicherung ist vorübergehend nicht verfügbar",
    );
    expect(screen.getByRole("button", { name: "Alles sichern" })).toBeEnabled();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
});
