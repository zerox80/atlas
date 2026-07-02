import React, { useState, useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FiSearch, FiFilter, FiX, FiChevronDown, FiArrowUp, FiArrowDown, FiDownload } from 'react-icons/fi'
import api, { exportContracts } from '../api'
import type { ContractFilterState } from '../utils/filterParams'

interface Tag {
    id: number
    name: string
    color: string
}

interface ContractList {
    id: number
    name: string
    color: string
    contract_count: number
}

interface SearchFilterBarProps {
    onFiltersChange: (filters: FilterState) => void
}

export type FilterState = ContractFilterState

const SearchFilterBar: React.FC<SearchFilterBarProps> = ({ onFiltersChange }) => {
    const [isExpanded, setIsExpanded] = useState(false)
    const [isExportMenuOpen, setIsExportMenuOpen] = useState(false)
    const [searchQuery, setSearchQuery] = useState('')
    const [selectedTags, setSelectedTags] = useState<string[]>([])
    const [selectedListId, setSelectedListId] = useState<number | null>(null)
    const [minValue, setMinValue] = useState('')
    const [maxValue, setMaxValue] = useState('')
    const [startDateFrom, setStartDateFrom] = useState('')
    const [startDateTo, setStartDateTo] = useState('')
    const [status, setStatus] = useState('')
    const [sortBy, setSortBy] = useState('uploaded_at')
    const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')

    // Fetch tags
    const { data: tags } = useQuery<Tag[]>(['tags'], async () => {
        const res = await api.get('/tags')
        return res.data
    })

    // Fetch lists
    const { data: lists } = useQuery<ContractList[]>(['lists'], async () => {
        const res = await api.get('/lists')
        return res.data
    })

    // Debounced search
    const [debouncedQuery, setDebouncedQuery] = useState('')
    useEffect(() => {
        const timer = setTimeout(() => {
            setDebouncedQuery(searchQuery)
        }, 300)
        return () => clearTimeout(timer)
    }, [searchQuery])

    // Build filters object
    const filters = useMemo<FilterState>(() => ({
        q: debouncedQuery,
        tags: selectedTags,
        listId: selectedListId,
        minValue,
        maxValue,
        startDateFrom,
        startDateTo,
        status,
        sortBy,
        sortOrder
    }), [debouncedQuery, selectedTags, selectedListId, minValue, maxValue, startDateFrom, startDateTo, status, sortBy, sortOrder])

    // Notify parent of filter changes
    useEffect(() => {
        onFiltersChange(filters)
    }, [filters, onFiltersChange])

    const handleTagToggle = (tagName: string) => {
        setSelectedTags(prev =>
            prev.includes(tagName)
                ? prev.filter(t => t !== tagName)
                : [...prev, tagName]
        )
    }

    const clearFilters = () => {
        setSearchQuery('')
        setSelectedTags([])
        setSelectedListId(null)
        setMinValue('')
        setMaxValue('')
        setStartDateFrom('')
        setStartDateTo('')
        setStatus('')
        setSortBy('uploaded_at')
        setSortOrder('desc')
    }

    const handleExport = async (format: 'csv' | 'excel') => {
        setIsExportMenuOpen(false);
        try {
            const response = await exportContracts(filters, format);
            const url = window.URL.createObjectURL(new Blob([response.data]));
            const link = document.createElement('a');
            link.href = url;
            link.setAttribute('download', `vertrage_export.${format === 'excel' ? 'xlsx' : 'csv'}`);
            document.body.appendChild(link);
            link.click();
            link.remove();
        } catch (e) {
            console.error("Export failed", e);
            alert("Fehler beim Exportieren der Verträge.");
        }
    }

    const hasActiveFilters = selectedTags.length > 0 || selectedListId !== null || minValue || maxValue || startDateFrom || startDateTo || status

    return (
        <div className="mb-6 space-y-4">
            {/* Search Bar */}
            <div className="flex gap-3">
                <div className="flex-1 relative">
                    <FiSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                    <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="Verträge durchsuchen..."
                        className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-10 pr-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 transition-colors"
                    />
                    {searchQuery && (
                        <button
                            onClick={() => setSearchQuery('')}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
                        >
                            <FiX />
                        </button>
                    )}
                </div>

                {/* Export Button */}
                <div className="relative">
                    <button
                        onClick={() => setIsExportMenuOpen(!isExportMenuOpen)}
                        className="flex items-center gap-2 px-4 py-2.5 bg-gray-800 border border-gray-700 hover:border-gray-600 text-gray-300 hover:text-white rounded-lg transition-colors"
                        title="Exportieren"
                    >
                        <FiDownload />
                        <span className="hidden md:inline">Export</span>
                        <FiChevronDown className={`transition-transform ${isExportMenuOpen ? 'rotate-180' : ''}`} />
                    </button>

                    {isExportMenuOpen && (
                        <div className="absolute right-0 mt-2 w-48 bg-gray-800 border border-gray-700 rounded-xl shadow-xl z-50 overflow-hidden animate-in fade-in zoom-in-95 duration-100">
                            <button
                                onClick={() => handleExport('excel')}
                                className="w-full text-left px-4 py-3 text-sm text-gray-300 hover:bg-gray-700 hover:text-white transition-colors border-b border-gray-700/50"
                            >
                                Als Excel (.xlsx)
                            </button>
                            <button
                                onClick={() => handleExport('csv')}
                                className="w-full text-left px-4 py-3 text-sm text-gray-300 hover:bg-gray-700 hover:text-white transition-colors"
                            >
                                Als CSV (.csv)
                            </button>
                        </div>
                    )}
                </div>

                <button
                    onClick={() => setIsExpanded(!isExpanded)}
                    className={`flex items-center gap-2 px-4 py-2 rounded-lg border transition-colors ${isExpanded || hasActiveFilters
                        ? 'bg-blue-600 border-blue-500 text-white'
                        : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-600'
                        }`}
                >
                    <FiFilter />
                    <span className="hidden md:inline">Filter</span>
                    {hasActiveFilters && (
                        <span className="bg-white/20 text-xs px-1.5 py-0.5 rounded-full">
                            {selectedTags.length + (selectedListId ? 1 : 0) + (status ? 1 : 0) + (minValue || maxValue ? 1 : 0) + (startDateFrom || startDateTo ? 1 : 0)}
                        </span>
                    )}
                    <FiChevronDown className={`transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                </button>
            </div>

            {/* Expanded Filters */}
            {isExpanded && (
                <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-4 space-y-4 animate-in slide-in-from-top-2">
                    {/* Tags */}
                    <div>
                        <label className="block text-sm font-medium text-gray-400 mb-2">Tags</label>
                        <div className="flex flex-wrap gap-2">
                            {tags?.map((tag) => (
                                <button
                                    key={tag.id}
                                    onClick={() => handleTagToggle(tag.name)}
                                    className={`px-3 py-1 rounded-full text-sm transition-colors ${selectedTags.includes(tag.name)
                                        ? 'bg-blue-600 text-white'
                                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                                        }`}
                                    style={selectedTags.includes(tag.name) ? { backgroundColor: tag.color } : {}}
                                >
                                    #{tag.name}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Lists */}
                    {lists && lists.length > 0 && (
                        <div>
                            <label className="block text-sm font-medium text-gray-400 mb-2">Liste</label>
                            <div className="flex flex-wrap gap-2">
                                <button
                                    onClick={() => setSelectedListId(null)}
                                    className={`px-3 py-1 rounded-full text-sm transition-colors ${selectedListId === null
                                        ? 'bg-blue-600 text-white'
                                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                                        }`}
                                >
                                    Alle
                                </button>
                                {lists.map((list) => (
                                    <button
                                        key={list.id}
                                        onClick={() => setSelectedListId(list.id)}
                                        className={`px-3 py-1 rounded-full text-sm transition-colors flex items-center gap-1 ${selectedListId === list.id
                                            ? 'text-white'
                                            : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                                            }`}
                                        style={selectedListId === list.id ? { backgroundColor: list.color } : {}}
                                    >
                                        <span
                                            className="w-2 h-2 rounded-full"
                                            style={{ backgroundColor: list.color }}
                                        />
                                        {list.name}
                                        <span className="text-xs opacity-70">({list.contract_count})</span>
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Status & Value Range */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-400 mb-2">Status</label>
                            <select
                                value={status}
                                onChange={(e) => setStatus(e.target.value)}
                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                            >
                                <option value="">Alle</option>
                                <option value="active">Aktiv</option>
                                <option value="expired">Abgelaufen</option>
                            </select>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-400 mb-2">Mindestwert (€)</label>
                            <input
                                type="text"
                                value={minValue}
                                onChange={(e) => setMinValue(e.target.value)}
                                placeholder="0"
                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-400 mb-2">Höchstwert (€)</label>
                            <input
                                type="text"
                                value={maxValue}
                                onChange={(e) => setMaxValue(e.target.value)}
                                placeholder="∞"
                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                            />
                        </div>
                    </div>

                    {/* Date Range */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-400 mb-2">Startdatum von</label>
                            <input
                                type="date"
                                value={startDateFrom}
                                onChange={(e) => setStartDateFrom(e.target.value)}
                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-400 mb-2">Startdatum bis</label>
                            <input
                                type="date"
                                value={startDateTo}
                                onChange={(e) => setStartDateTo(e.target.value)}
                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                            />
                        </div>
                    </div>

                    {/* Sorting */}
                    <div className="flex flex-wrap gap-4 items-end">
                        <div className="flex-1 min-w-[200px]">
                            <label className="block text-sm font-medium text-gray-400 mb-2">Sortieren nach</label>
                            <select
                                value={sortBy}
                                onChange={(e) => setSortBy(e.target.value)}
                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                            >
                                <option value="uploaded_at">Hochgeladen am</option>
                                <option value="title">Name</option>
                                <option value="value">Wert</option>
                                <option value="start_date">Startdatum</option>
                                <option value="end_date">Enddatum</option>
                            </select>
                        </div>
                        <button
                            onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')}
                            className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-gray-300 transition-colors"
                        >
                            {sortOrder === 'asc' ? <FiArrowUp /> : <FiArrowDown />}
                            {sortOrder === 'asc' ? 'Aufsteigend' : 'Absteigend'}
                        </button>
                        {hasActiveFilters && (
                            <button
                                onClick={clearFilters}
                                className="px-4 py-2 bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded-lg transition-colors"
                            >
                                Filter zurücksetzen
                            </button>
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}

export default SearchFilterBar
