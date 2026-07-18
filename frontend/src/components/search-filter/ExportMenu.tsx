import { useState } from "react";
import { FiChevronDown, FiDownload } from "react-icons/fi";
import { exportContracts } from "../../api";
import { triggerBlobDownload } from "../../utils/downloadUtils";
import { getApiErrorMessage } from "../../utils/errorUtils";
import type { FilterState } from "./useContractFilters";

interface ExportMenuProps {
  filters: FilterState;
  filterError: string | null;
}

const ExportMenu = ({ filters, filterError }: ExportMenuProps) => {
  const [isOpen, setIsOpen] = useState(false);

  const handleExport = async (format: "csv" | "excel") => {
    setIsOpen(false);
    if (filterError) {
      alert(filterError);
      return;
    }
    try {
      const response = await exportContracts(filters, format);
      triggerBlobDownload(
        response.data,
        `vertrage_export.${format === "excel" ? "xlsx" : "csv"}`,
      );
    } catch (error: unknown) {
      console.error("Export failed", error);
      alert(getApiErrorMessage(error, "Fehler beim Exportieren der Verträge."));
    }
  };

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen((current) => !current)}
        className={[
          "flex items-center gap-2 px-4 py-2.5 bg-gray-800 border border-gray-700",
          "hover:border-gray-600 text-gray-300 hover:text-white rounded-lg",
          "transition-colors",
        ].join(" ")}
        title="Exportieren"
      >
        <FiDownload />
        <span className="hidden md:inline">Export</span>
        <FiChevronDown
          className={`transition-transform ${isOpen ? "rotate-180" : ""}`}
        />
      </button>
      {isOpen && (
        <div
          className={[
            "absolute right-0 mt-2 w-48 bg-gray-800 border border-gray-700 rounded-xl",
            "shadow-xl z-50 overflow-hidden animate-in fade-in zoom-in-95 duration-100",
          ].join(" ")}
        >
          <button
            onClick={() => handleExport("excel")}
            className="w-full border-b border-gray-700/50 px-4 py-3 text-left text-sm text-gray-300 transition-colors hover:bg-gray-700 hover:text-white"
          >
            Als Excel (.xlsx)
          </button>
          <button
            onClick={() => handleExport("csv")}
            className="w-full px-4 py-3 text-left text-sm text-gray-300 transition-colors hover:bg-gray-700 hover:text-white"
          >
            Als CSV (.csv)
          </button>
        </div>
      )}
    </div>
  );
};

export default ExportMenu;
