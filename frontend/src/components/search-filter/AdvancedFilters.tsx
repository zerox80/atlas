import type { ReactNode } from "react";
import { FiArrowDown, FiArrowUp } from "react-icons/fi";
import type { ContractFilterController } from "./useContractFilters";

interface AdvancedFiltersProps {
  controller: ContractFilterController;
}

const fieldClass = [
  "w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2",
  "text-white focus:border-blue-500 focus:outline-none",
].join(" ");

const FieldLabel = ({ children }: { children: ReactNode }) => (
  <label className="mb-2 block text-sm font-medium text-gray-400">
    {children}
  </label>
);

const AdvancedFilters = ({ controller }: AdvancedFiltersProps) => (
  <div className="animate-in space-y-4 rounded-xl border border-gray-700 bg-gray-800/50 p-4 slide-in-from-top-2">
    <div>
      <FieldLabel>Tags</FieldLabel>
      <div className="flex flex-wrap gap-2">
        {controller.tags?.map((tag) => {
          const isSelected = controller.selectedTags.includes(tag.name);
          return (
            <button
              key={tag.id}
              onClick={() => controller.toggleTag(tag.name)}
              className={`rounded-full px-3 py-1 text-sm transition-colors ${
                isSelected
                  ? "bg-blue-600 text-white"
                  : "bg-gray-700 text-gray-300 hover:bg-gray-600"
              }`}
              style={isSelected ? { backgroundColor: tag.color } : {}}
            >
              #{tag.name}
            </button>
          );
        })}
      </div>
    </div>

    {controller.lists && controller.lists.length > 0 && (
      <div>
        <FieldLabel>Liste</FieldLabel>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => controller.setSelectedListId(null)}
            className={`rounded-full px-3 py-1 text-sm transition-colors ${
              controller.selectedListId === null
                ? "bg-blue-600 text-white"
                : "bg-gray-700 text-gray-300 hover:bg-gray-600"
            }`}
          >
            Alle
          </button>
          {controller.lists.map((list) => {
            const isSelected = controller.selectedListId === list.id;
            return (
              <button
                key={list.id}
                onClick={() => controller.setSelectedListId(list.id)}
                className={`flex items-center gap-1 rounded-full px-3 py-1 text-sm transition-colors ${
                  isSelected
                    ? "text-white"
                    : "bg-gray-700 text-gray-300 hover:bg-gray-600"
                }`}
                style={isSelected ? { backgroundColor: list.color } : {}}
              >
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ backgroundColor: list.color }}
                />
                {list.name}
                <span className="text-xs opacity-70">
                  ({list.contract_count})
                </span>
              </button>
            );
          })}
        </div>
      </div>
    )}

    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      <div>
        <FieldLabel>Status</FieldLabel>
        <select
          value={controller.status}
          onChange={(event) => controller.setStatus(event.target.value)}
          className={fieldClass}
        >
          <option value="">Alle</option>
          <option value="active">Aktiv</option>
          <option value="expired">Abgelaufen</option>
        </select>
      </div>
      <div>
        <FieldLabel>Mindestwert (€)</FieldLabel>
        <input
          type="text"
          value={controller.minValue}
          onChange={(event) => controller.setMinValue(event.target.value)}
          placeholder="0"
          className={fieldClass}
        />
      </div>
      <div>
        <FieldLabel>Höchstwert (€)</FieldLabel>
        <input
          type="text"
          value={controller.maxValue}
          onChange={(event) => controller.setMaxValue(event.target.value)}
          placeholder="∞"
          className={fieldClass}
        />
      </div>
    </div>
    {controller.filterError && (
      <p className="text-sm text-red-400" role="alert">
        {controller.filterError}
      </p>
    )}

    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <div>
        <FieldLabel>Startdatum von</FieldLabel>
        <input
          type="date"
          value={controller.startDateFrom}
          onChange={(event) => controller.setStartDateFrom(event.target.value)}
          className={fieldClass}
        />
      </div>
      <div>
        <FieldLabel>Startdatum bis</FieldLabel>
        <input
          type="date"
          value={controller.startDateTo}
          onChange={(event) => controller.setStartDateTo(event.target.value)}
          className={fieldClass}
        />
      </div>
    </div>

    <div className="flex flex-wrap items-end gap-4">
      <div className="min-w-[200px] flex-1">
        <FieldLabel>Sortieren nach</FieldLabel>
        <select
          value={controller.sortBy}
          onChange={(event) => controller.setSortBy(event.target.value)}
          className={fieldClass}
        >
          <option value="uploaded_at">Hochgeladen am</option>
          <option value="title">Name</option>
          <option value="value">Wert</option>
          <option value="start_date">Startdatum</option>
          <option value="end_date">Enddatum</option>
        </select>
      </div>
      <button
        onClick={() =>
          controller.setSortOrder(
            controller.sortOrder === "asc" ? "desc" : "asc",
          )
        }
        className="flex items-center gap-2 rounded-lg bg-gray-700 px-4 py-2 text-gray-300 transition-colors hover:bg-gray-600"
      >
        {controller.sortOrder === "asc" ? <FiArrowUp /> : <FiArrowDown />}
        {controller.sortOrder === "asc" ? "Aufsteigend" : "Absteigend"}
      </button>
      {controller.activeFilterCount > 0 && (
        <button
          onClick={controller.clearFilters}
          className="rounded-lg bg-red-900/30 px-4 py-2 text-red-400 transition-colors hover:bg-red-900/50"
        >
          Filter zurücksetzen
        </button>
      )}
    </div>
  </div>
);

export default AdvancedFilters;
