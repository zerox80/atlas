import React from "react";
import { FiSearch } from "react-icons/fi";
import { contractViewFilters, type ContractFilterCounts, type ContractViewFilter } from "./types";

interface ContractToolbarProps {
  counts: ContractFilterCounts;
  filter: ContractViewFilter;
  onFilterChange: (filter: ContractViewFilter) => void;
  searchQuery: string;
  onSearchChange: (searchQuery: string) => void;
}

const ContractToolbar: React.FC<ContractToolbarProps> = ({
  counts,
  filter,
  onFilterChange,
  searchQuery,
  onSearchChange,
}) => (
  <div className="surface mb-5 flex flex-col gap-3 p-3 lg:flex-row lg:items-center lg:justify-between">
    <div className="flex gap-1 overflow-x-auto">
      {contractViewFilters.map(({ key, label }) => (
        <button
          key={key}
          onClick={() => onFilterChange(key)}
          className={[
            "flex shrink-0 items-center gap-2 rounded-xl px-3.5 py-2.5",
            "text-sm font-semibold transition",
            filter === key
              ? "bg-white/[0.09] text-white"
              : "text-[#7f8999] hover:text-white",
          ].join(" ")}
        >
          {label}
          <span
            className={[
              "rounded-full px-1.5 py-0.5 text-[10px]",
              filter === key
                ? "bg-[#b8f15a] text-[#111700]"
                : "bg-white/[0.06]",
            ].join(" ")}
          >
            {counts[key]}
          </span>
        </button>
      ))}
    </div>
    <label className="relative block min-w-0 lg:w-72">
      <FiSearch className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#667181]" />
      <input
        value={searchQuery}
        maxLength={200}
        onChange={(event) => onSearchChange(event.target.value)}
        placeholder="Verträge durchsuchen…"
        className="field py-2.5 pl-10"
      />
    </label>
  </div>
);

export default ContractToolbar;
