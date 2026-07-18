import { FiChevronDown, FiFilter, FiSearch, FiX } from "react-icons/fi";
import ExportMenu from "./ExportMenu";
import type { ContractFilterController } from "./useContractFilters";

interface FilterToolbarProps {
  controller: ContractFilterController;
}

const FilterToolbar = ({ controller }: FilterToolbarProps) => (
  <div className="flex gap-3">
    <div className="relative flex-1">
      <FiSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
      <input
        type="text"
        value={controller.searchQuery}
        onChange={(event) => controller.setSearchQuery(event.target.value)}
        placeholder="Verträge durchsuchen..."
        className={[
          "w-full rounded-lg border border-gray-700 bg-gray-800 py-2.5 pl-10 pr-4",
          "text-white placeholder-gray-500 transition-colors focus:border-blue-500 focus:outline-none",
        ].join(" ")}
      />
      {controller.searchQuery && (
        <button
          onClick={() => controller.setSearchQuery("")}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
        >
          <FiX />
        </button>
      )}
    </div>

    <ExportMenu
      filters={controller.filters}
      filterError={controller.filterError}
    />

    <button
      onClick={() => controller.setIsExpanded((current) => !current)}
      className={`flex items-center gap-2 rounded-lg border px-4 py-2 transition-colors ${
        controller.isExpanded || controller.activeFilterCount > 0
          ? "border-blue-500 bg-blue-600 text-white"
          : "border-gray-700 bg-gray-800 text-gray-300 hover:border-gray-600"
      }`}
    >
      <FiFilter />
      <span className="hidden md:inline">Filter</span>
      {controller.activeFilterCount > 0 && (
        <span className="rounded-full bg-white/20 px-1.5 py-0.5 text-xs">
          {controller.activeFilterCount}
        </span>
      )}
      <FiChevronDown
        className={`transition-transform ${controller.isExpanded ? "rotate-180" : ""}`}
      />
    </button>
  </div>
);

export default FilterToolbar;
