import AdvancedFilters from "./search-filter/AdvancedFilters";
import FilterToolbar from "./search-filter/FilterToolbar";
import {
  useContractFilters,
  type FilterState,
} from "./search-filter/useContractFilters";

interface SearchFilterBarProps {
  onFiltersChange: (filters: FilterState) => void;
}

export type { FilterState } from "./search-filter/useContractFilters";

const SearchFilterBar = ({ onFiltersChange }: SearchFilterBarProps) => {
  const controller = useContractFilters(onFiltersChange);

  return (
    <div className="mb-6 space-y-4">
      <FilterToolbar controller={controller} />
      {controller.isExpanded && <AdvancedFilters controller={controller} />}
    </div>
  );
};

export default SearchFilterBar;
