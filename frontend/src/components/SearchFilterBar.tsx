import type { DocumentType } from "../types";
import AdvancedFilters from "./search-filter/AdvancedFilters";
import FilterToolbar from "./search-filter/FilterToolbar";
import {
  useContractFilters,
  type FilterState,
} from "./search-filter/useContractFilters";

interface SearchFilterBarProps {
  documentType?: DocumentType;
  fixedListId?: number | null;
  onFiltersChange: (filters: FilterState) => void;
}

export type { FilterState } from "./search-filter/useContractFilters";

const SearchFilterBar = ({
  documentType = "contract",
  fixedListId,
  onFiltersChange,
}: SearchFilterBarProps) => {
  const controller = useContractFilters(onFiltersChange, fixedListId);

  return (
    <div className="mb-6 space-y-4">
      <FilterToolbar controller={controller} documentType={documentType} />
      {controller.isExpanded && <AdvancedFilters controller={controller} />}
    </div>
  );
};

export default SearchFilterBar;
