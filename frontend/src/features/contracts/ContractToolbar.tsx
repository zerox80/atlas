import React from "react";
import {
  contractViewFilters,
  type ContractFilterCounts,
  type ContractViewFilter,
} from "./types";

interface ContractToolbarProps {
  counts: ContractFilterCounts;
  filter: ContractViewFilter;
  onFilterChange: (filter: ContractViewFilter) => void;
}

const ContractToolbar: React.FC<ContractToolbarProps> = ({
  counts,
  filter,
  onFilterChange,
}) => (
  <div className="surface mb-5 p-3">
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
  </div>
);

export default ContractToolbar;
