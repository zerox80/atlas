import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import api from "../../api";
import { queryKeys } from "../../queryKeys";
import type { ContractList, Tag } from "../../types";
import {
  getContractFilterValidationError,
  type ContractFilterState,
} from "../../utils/filterParams";

export type FilterState = ContractFilterState;

export const useContractFilters = (
  onFiltersChange: (filters: FilterState) => void,
) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [selectedListId, setSelectedListId] = useState<number | null>(null);
  const [minValue, setMinValue] = useState("");
  const [maxValue, setMaxValue] = useState("");
  const [startDateFrom, setStartDateFrom] = useState("");
  const [startDateTo, setStartDateTo] = useState("");
  const [status, setStatus] = useState("");
  const [sortBy, setSortBy] = useState("uploaded_at");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");

  const { data: tags } = useQuery<Tag[]>(queryKeys.tags, async () => {
    const response = await api.get<Tag[]>("/tags");
    return response.data;
  });
  const { data: lists } = useQuery<ContractList[]>(queryKeys.lists, async () => {
    const response = await api.get<ContractList[]>("/lists");
    return response.data;
  });

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(searchQuery), 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const filters = useMemo<FilterState>(
    () => ({
      q: debouncedQuery,
      tags: selectedTags,
      listId: selectedListId,
      minValue,
      maxValue,
      startDateFrom,
      startDateTo,
      status,
      sortBy,
      sortOrder,
    }),
    [
      debouncedQuery,
      selectedTags,
      selectedListId,
      minValue,
      maxValue,
      startDateFrom,
      startDateTo,
      status,
      sortBy,
      sortOrder,
    ],
  );
  const filterError = useMemo(
    () => getContractFilterValidationError(filters),
    [filters],
  );

  useEffect(() => {
    if (!filterError) onFiltersChange(filters);
  }, [filterError, filters, onFiltersChange]);

  const toggleTag = (tagName: string) => {
    setSelectedTags((current) =>
      current.includes(tagName)
        ? current.filter((tag) => tag !== tagName)
        : [...current, tagName],
    );
  };

  const clearFilters = () => {
    setSearchQuery("");
    setSelectedTags([]);
    setSelectedListId(null);
    setMinValue("");
    setMaxValue("");
    setStartDateFrom("");
    setStartDateTo("");
    setStatus("");
    setSortBy("uploaded_at");
    setSortOrder("desc");
  };

  const activeFilterCount =
    selectedTags.length +
    (selectedListId !== null ? 1 : 0) +
    (status ? 1 : 0) +
    (minValue || maxValue ? 1 : 0) +
    (startDateFrom || startDateTo ? 1 : 0);

  return {
    activeFilterCount,
    clearFilters,
    filterError,
    filters,
    isExpanded,
    lists,
    maxValue,
    minValue,
    searchQuery,
    selectedListId,
    selectedTags,
    setIsExpanded,
    setMaxValue,
    setMinValue,
    setSearchQuery,
    setSelectedListId,
    setSortBy,
    setSortOrder,
    setStartDateFrom,
    setStartDateTo,
    setStatus,
    sortBy,
    sortOrder,
    startDateFrom,
    startDateTo,
    status,
    tags,
    toggleTag,
  };
};

export type ContractFilterController = ReturnType<typeof useContractFilters>;
