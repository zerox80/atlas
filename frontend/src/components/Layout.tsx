import React from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  FiBarChart2,
  FiCalendar,
  FiChevronDown,
  FiCommand,
  FiFileText,
  FiFolder,
  FiLogOut,
  FiMenu,
  FiPlus,
  FiSearch,
  FiShield,
  FiX,
} from "react-icons/fi";
import { useUser } from "../App";
import api from "../api";
import CommandPalette from "./CommandPalette";
import ThemeToggle from "./ThemeToggle";
import UploadModal from "./UploadModal";

interface LayoutProps {
  children: React.ReactNode;
}

const primaryNav = [
  { to: "/", label: "Dashboard", icon: FiBarChart2, end: true },
  { to: "/contracts", label: "Verträge", icon: FiFileText },
  { to: "/invoices", label: "Rechnungen", icon: FiFileText },
  { to: "/calendar", label: "Kalender", icon: FiCalendar },
];

const workspaceNav = [
  { to: "/lists", label: "Sammlungen", icon: FiFolder },
  { to: "/protected", label: "Geschützt", icon: FiShield },
];

const pageMeta: Record<string, { eyebrow: string; title: string }> = {
  "/": { eyebrow: "Übersicht", title: "Command Center" },
  "/contracts": { eyebrow: "Dokumente", title: "Verträge" },
  "/invoices": { eyebrow: "Dokumente", title: "Rechnungen" },
  "/calendar": { eyebrow: "Planung", title: "Kalender" },
  "/lists": { eyebrow: "Workspace", title: "Sammlungen" },
  "/protected": { eyebrow: "Sicherheit", title: "Geschützte Dokumente" },
  "/admin": { eyebrow: "System", title: "Administration" },
};

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [createOpen, setCreateOpen] = React.useState(false);
  const [createType, setCreateType] = React.useState<
    "contract" | "invoice" | null
  >(null);
  const { user, isAdmin } = useUser();
  const meta = pageMeta[location.pathname] || pageMeta["/"];

  React.useEffect(() => {
    setMobileOpen(false);
    setCreateOpen(false);
  }, [location.pathname]);

  const handleLogout = async () => {
    try {
      await api.post("/logout");
    } catch {
      /* local logout still proceeds */
    }
    navigate("/login");
    window.location.reload();
  };

  const openCommand = () =>
    window.dispatchEvent(new CustomEvent("atlas:command"));

  const renderLink = ({
    to,
    label,
    icon: Icon,
    end,
  }: (typeof primaryNav)[number]) => (
    <NavLink
      key={to}
      to={to}
      end={end}
      className={({ isActive }) =>
        [
          "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition",
          isActive
            ? "bg-white/[0.09] text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,.06)]"
            : "text-[#8f99a9] hover:bg-white/[0.05] hover:text-white",
        ].join(" ")
      }
    >
      {({ isActive }) => (
        <>
          <span
            className={[
              "flex h-8 w-8 items-center justify-center rounded-lg transition",
              isActive
                ? "bg-[#b8f15a] text-[#111700]"
                : "bg-white/[0.04] text-[#7c8798] group-hover:text-white",
            ].join(" ")}
          >
            <Icon size={16} />
          </span>
          <span>{label}</span>
          {isActive && (
            <span className="ml-auto h-1.5 w-1.5 rounded-full bg-[#b8f15a]" />
          )}
        </>
      )}
    </NavLink>
  );

  const sidebar = (
    <aside
      className={[
        "flex h-full w-[280px] flex-col border-r border-white/[0.07]",
        "bg-[#0b0e13]/95 px-4 py-5 backdrop-blur-xl",
      ].join(" ")}
    >
      <div className="mb-7 flex items-center justify-between px-2">
        <button
          onClick={() => navigate("/")}
          className="flex items-center gap-3 text-left"
        >
          <span
            className={[
              "relative flex h-10 w-10 items-center justify-center overflow-hidden",
              "rounded-[14px] bg-[#b8f15a] font-black tracking-[-0.08em] text-[#111700]",
            ].join(" ")}
          >
            AT
            <span className="absolute -bottom-3 -right-2 h-7 w-7 rounded-full border-[5px] border-[#111700]/10" />
          </span>
          <span>
            <strong className="block text-sm font-bold tracking-wide text-white">
              Atlas
            </strong>
            <span className="block text-[11px] text-[#687282]">
              Document operations
            </span>
          </span>
        </button>
        <button
          onClick={() => setMobileOpen(false)}
          className="icon-btn lg:hidden"
          aria-label="Menü schließen"
        >
          <FiX />
        </button>
      </div>

      <button
        onClick={openCommand}
        className={[
          "mb-6 flex h-11 items-center gap-3 rounded-xl border border-white/[0.08]",
          "bg-white/[0.035] px-3 text-sm text-[#758091] transition",
          "hover:border-white/[0.14] hover:bg-white/[0.06] hover:text-white",
        ].join(" ")}
      >
        <FiSearch />
        <span className="flex-1 text-left">Suchen & öffnen</span>
        <kbd className="rounded-md border border-white/[0.09] bg-black/20 px-1.5 py-0.5 text-[10px] text-[#626c7c]">
          ⌘ K
        </kbd>
      </button>

      <nav className="flex-1 overflow-y-auto">
        <p className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[0.18em] text-[#4e5867]">
          Arbeitsbereich
        </p>
        <div className="space-y-1">{primaryNav.map(renderLink)}</div>
        <p className="mb-2 mt-7 px-3 text-[10px] font-bold uppercase tracking-[0.18em] text-[#4e5867]">
          Organisation
        </p>
        <div className="space-y-1">{workspaceNav.map(renderLink)}</div>
        {isAdmin && (
          <div className="mt-7 border-t border-white/[0.06] pt-4">
            {renderLink({
              to: "/admin",
              label: "Administration",
              icon: FiShield,
            })}
          </div>
        )}
      </nav>

      <div className="mt-4 rounded-2xl border border-white/[0.07] bg-white/[0.035] p-3">
        <div className="flex items-center gap-3">
          <span
            className={[
              "flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br",
              "from-[#77a7ff] to-[#b28cff] text-sm font-bold text-white",
            ].join(" ")}
          >
            {user?.username?.slice(0, 2).toUpperCase() || "AT"}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-white">
              {user?.username || "Benutzer"}
            </p>
            <p className="text-[11px] capitalize text-[#697384]">
              {user?.role || "Workspace"}
            </p>
          </div>
          <button
            onClick={handleLogout}
            className="icon-btn h-9 w-9 border-0 bg-transparent"
            title="Abmelden"
            aria-label="Abmelden"
          >
            <FiLogOut />
          </button>
        </div>
      </div>
    </aside>
  );

  return (
    <div className="min-h-screen bg-transparent text-white">
      <CommandPalette />
      <div className="fixed inset-y-0 left-0 z-40 hidden lg:block">
        {sidebar}
      </div>
      {mobileOpen && (
        <>
          <button
            className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm lg:hidden"
            onClick={() => setMobileOpen(false)}
            aria-label="Menü schließen"
          />
          <div className="fixed inset-y-0 left-0 z-50 lg:hidden">{sidebar}</div>
        </>
      )}

      <div className="min-h-screen lg:pl-[280px]">
        <header
          className={[
            "sticky top-0 z-30 flex h-[72px] items-center gap-3 border-b",
            "border-white/[0.06] bg-[#090c11]/80 px-4 backdrop-blur-xl sm:px-6",
            "lg:px-8",
          ].join(" ")}
        >
          <button
            onClick={() => setMobileOpen(true)}
            className="icon-btn lg:hidden"
            aria-label="Menü öffnen"
          >
            <FiMenu />
          </button>
          <div className="min-w-0 flex-1">
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[#687282]">
              {meta.eyebrow}
            </p>
            <p className="truncate text-sm font-semibold text-[#e9edf3]">
              {meta.title}
            </p>
          </div>
          <button
            onClick={openCommand}
            className="btn-ghost hidden sm:inline-flex"
          >
            <FiCommand />
            <span>Command</span>
            <kbd className="ml-1 rounded-md border border-white/[0.09] px-1.5 py-0.5 text-[10px] text-[#697384]">
              Ctrl K
            </kbd>
          </button>
          <ThemeToggle />
          {user?.can_create_documents && <div className="relative">
            <button
              onClick={() => setCreateOpen(!createOpen)}
              className="btn-primary"
            >
              <FiPlus />
              <span className="hidden sm:inline">Neu anlegen</span>
              <FiChevronDown
                className={`transition ${createOpen ? "rotate-180" : ""}`}
              />
            </button>
            {createOpen && (
              <div className="surface-raised absolute right-0 top-12 w-56 p-2">
                <button
                  onClick={() => {
                    setCreateType("contract");
                    setCreateOpen(false);
                  }}
                  className={[
                    "flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-sm",
                    "text-[#cbd2dc] hover:bg-white/[0.06] hover:text-white",
                  ].join(" ")}
                >
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#b8f15a]/10 text-[#b8f15a]">
                    <FiFileText />
                  </span>
                  <span>
                    <strong className="block text-sm">Vertrag</strong>
                    <small className="text-[#657080]">mit Fristen & KI</small>
                  </span>
                </button>
                <button
                  onClick={() => {
                    setCreateType("invoice");
                    setCreateOpen(false);
                  }}
                  className={[
                    "flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-sm",
                    "text-[#cbd2dc] hover:bg-white/[0.06] hover:text-white",
                  ].join(" ")}
                >
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#7397ff]/10 text-[#7397ff]">
                    <FiFileText />
                  </span>
                  <span>
                    <strong className="block text-sm">Rechnung</strong>
                    <small className="text-[#657080]">schnell erfassen</small>
                  </span>
                </button>
              </div>
            )}
          </div>}
        </header>
        <main>{children}</main>
      </div>
      <UploadModal
        isOpen={createType !== null}
        onClose={() => setCreateType(null)}
        documentType={createType || "contract"}
        initialListId={
          Number(new URLSearchParams(location.search).get("list_id")) || null
        }
      />
    </div>
  );
};

export default Layout;
