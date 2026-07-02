import React, { useState, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { FiPlus, FiDownload, FiCalendar, FiClock, FiTrash2, FiFolder, FiShield, FiLock } from 'react-icons/fi'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RechartsTooltip, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts'
import api, { toggleContractProtection } from '../api'
import { formatGermanNumber } from '../utils/formatUtils'
import { buildContractQueryParams } from '../utils/filterParams'
import UploadModal from '../components/UploadModal'
import CommandPalette from '../components/CommandPalette'
import AuditModal from '../components/AuditModal'
import SearchFilterBar, { FilterState } from '../components/SearchFilterBar'
import AddToListModal from '../components/AddToListModal'
import { useUser } from '../App'

interface Contract {
    id: number
    title: string
    description?: string | null
    start_date?: string
    end_date?: string
    uploaded_at: string
    value?: number | null
    annual_value?: number | null
    tags: { name: string, color: string }[]
    lists?: { id: number, name: string, color: string }[]
    version?: number
    notice_period?: number | null
    file_extension: string
    is_protected: boolean
    can_read: boolean
    can_write: boolean
    can_delete: boolean
    can_manage_protection: boolean
}

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

const formatContractDate = (date?: string | null) => (
    date ? new Date(date).toLocaleDateString('de-DE') : '-'
)

const isExpired = (endDate?: string | null) => (
    Boolean(endDate && new Date(endDate) < new Date())
)

const getStatusLabel = (endDate?: string | null) => {
    if (!endDate) return 'Unbefristet'
    return isExpired(endDate) ? 'Abgelaufen' : 'Aktiv'
}

const getStatusClass = (endDate?: string | null) => {
    if (!endDate) return 'bg-gray-700 text-gray-300'
    return isExpired(endDate) ? 'bg-red-900/50 text-red-300' : 'bg-emerald-900/50 text-emerald-300'
}

const Dashboard: React.FC = () => {
    const [searchParams] = useSearchParams()
    const { isAdmin } = useUser()
    const [isUploadOpen, setIsUploadOpen] = useState(false)
    const [isAuditOpen, setIsAuditOpen] = useState(false)
    const [auditContract, setAuditContract] = useState<{ id: number, title: string } | null>(null)
    const [editingContract, setEditingContract] = useState<Contract | null>(null)
    const [isAddToListOpen, setIsAddToListOpen] = useState(false)
    const [addToListContract, setAddToListContract] = useState<{ id: number, title: string } | null>(null)
    const [filters, setFilters] = useState<FilterState | null>(null)
    const queryClient = useQueryClient()

    // Check for list_id in URL params (from Lists page navigation)
    const urlListId = searchParams.get('list_id')

    const handleFiltersChange = useCallback((newFilters: FilterState) => {
        setFilters(newFilters)
    }, [])

    const { data: contracts, isLoading } = useQuery<Contract[]>(
        ['contracts', filters, urlListId],
        async () => {
            const params = buildContractQueryParams(filters)

            // URL list_id takes precedence (from Lists page navigation)
            if (urlListId && !filters?.listId) {
                params.list_id = parseInt(urlListId)
            }

            const res = await api.get('/contracts', { params })
            return res.data
        }
    )

    const handleDelete = async (id: number, title: string, isProtected: boolean) => {
        if (isProtected) {
            alert('Dieser Vertrag ist geschützt. Bitte heben Sie den Schutz in der "Geschützte Verträge" Übersicht auf, bevor Sie ihn löschen.');
            return;
        }

        if (window.confirm(`Möchten Sie den Vertrag "${title}" wirklich löschen?`)) {
            try {
                await api.delete(`/contracts/${id}`)
                queryClient.invalidateQueries(['contracts'])
            } catch (e) {
                console.error("Delete failed", e)
                alert("Fehler beim Löschen des Vertrags")
            }
        }
    }

    const handleToggleProtection = async (id: number, currentStatus: boolean, title: string) => {
        const action = currentStatus ? "aufheben" : "aktivieren";
        if (!window.confirm(`Möchten Sie den Schutz für "${title}" wirklich ${action}?`)) {
            return;
        }

        try {
            await toggleContractProtection(id);
            queryClient.invalidateQueries(['contracts']);
        } catch (e) {
            console.error("Protection toggle failed", e);
            alert("Fehler beim Ändern des Schutz-Status.");
        }
    }

    // Analytics
    const activeContracts = contracts?.length || 0;
    const totalValue = contracts?.reduce((acc, c) => acc + (c.value || 0), 0) || 0;

    // State for spending chart year filter
    const currentYear = new Date().getFullYear();
    const [selectedYear, setSelectedYear] = useState(currentYear);

    // Calculate available years for filter
    const availableYears = React.useMemo(() => {
        if (!contracts) return [currentYear];
        const years = new Set<number>();
        years.add(currentYear);
        contracts.forEach(c => {
            if (c.start_date) {
                years.add(new Date(c.start_date).getFullYear());
            }
        });
        return Array.from(years).sort((a, b) => b - a);
    }, [contracts, currentYear]);

    // Group by month for spending chart, filtered by selected year
    const spendingData = React.useMemo(() => {
        if (!contracts) return [];

        const months: { [key: string]: number } = {};
        const allMonths = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];

        allMonths.forEach(m => months[m] = 0);

        contracts.forEach(contract => {
            if (!contract.start_date || !contract.value) return;
            const date = new Date(contract.start_date);

            // Filter by selected year
            if (date.getFullYear() !== selectedYear) return;

            const monthIndex = date.getMonth();
            const monthName = allMonths[monthIndex];
            if (months[monthName] !== undefined) {
                months[monthName] += contract.value;
            }
        });

        return allMonths.map(name => ({
            name,
            amount: months[name]
        }));
    }, [contracts, selectedYear]);

    // Cost Distribution (Donut Chart)
    const costDistributionData = React.useMemo(() => {
        if (!contracts) return [];
        const sorted = [...contracts].sort((a, b) => (b.value || 0) - (a.value || 0));

        const topItems = sorted.slice(0, 4);
        const others = sorted.slice(4);

        const data = topItems.map(c => ({ name: c.title, value: c.value || 0 }));

        if (others.length > 0) {
            const othersValue = others.reduce((acc, c) => acc + (c.value || 0), 0);
            data.push({ name: 'Andere', value: othersValue });
        }

        return data.filter(d => d.value > 0);
    }, [contracts]);

    const handleDownload = async (id: number, title: string, extension: string) => {
        try {
            const response = await api.get(`/contracts/${id}/download`, {
                responseType: 'blob'
            });
            // Normalize extension (ensure it has a dot)
            let ext = extension || '.pdf';
            if (!ext.startsWith('.')) {
                ext = '.' + ext;
            }

            const isPdf = ext.toLowerCase() === '.pdf';
            const blobType = isPdf ? 'application/pdf' : undefined;
            const url = window.URL.createObjectURL(new Blob([response.data], { type: blobType }));
            const link = document.createElement('a');
            link.href = url;

            const filename = title.endsWith(ext) ? title : `${title}${ext}`;
            link.setAttribute('download', filename);
            document.body.appendChild(link);
            link.click();
            link.remove();
        } catch (e: any) {
            console.error("Download failed", e)
            if (e.response && e.response.status === 404) {
                alert("Datei wurde auf dem Server nicht gefunden. Bitte laden Sie die Datei erneut hoch.");
            } else {
                alert("Fehler beim Herunterladen der Datei.");
            }
        }
    }

    if (isLoading) return <div className="p-8 text-center text-gray-400">Lade Dashboard...</div>

    return (
        <div className="w-full bg-gray-950 p-0 md:p-8">
            <CommandPalette />

            <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8 p-4 md:p-0">
                <div>
                    <h1 className="text-3xl font-bold text-white mb-2">Vertragsübersicht</h1>
                    <p className="text-gray-400">Verwalten und verfolgen Sie Ihre Unternehmensvereinbarungen.</p>
                </div>
                <button
                    onClick={() => setIsUploadOpen(true)}
                    className="mt-4 md:mt-0 w-full md:w-auto flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg font-medium transition-colors shadow-lg shadow-blue-500/20"
                >
                    <FiPlus />
                    <span>Neuer Vertrag</span>
                </button>
            </div>

            {/* Search and Filter Bar */}
            <SearchFilterBar onFiltersChange={handleFiltersChange} />

            {/* Analytics Row */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
                <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-6 backdrop-blur-sm">
                    <h3 className="text-gray-400 text-sm font-medium mb-2">Gesamtwert</h3>
                    <p className="text-2xl lg:text-3xl font-bold text-green-400 break-all sm:break-normal">{totalValue.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}</p>
                </div>
                <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-6 backdrop-blur-sm">
                    <h3 className="text-gray-400 text-sm font-medium mb-2">Aktive Verträge</h3>
                    <p className="text-3xl font-bold text-white">{activeContracts}</p>
                </div>

                <div className="md:col-span-2 bg-gray-800/50 border border-gray-700 rounded-xl p-4 backdrop-blur-sm flex flex-col md:flex-row gap-4 min-w-0">
                    {/* Bar Chart Section */}
                    <div className="flex-1 min-w-0">
                        <div className="flex justify-between items-center mb-2">
                            <p className="text-xs text-gray-400">Ausgabentrend ({selectedYear})</p>
                            <select
                                value={selectedYear}
                                onChange={(e) => setSelectedYear(parseInt(e.target.value))}
                                className="bg-gray-700 border border-gray-600 text-xs text-white rounded px-2 py-1 outline-none focus:border-blue-500"
                            >
                                {availableYears.map(year => (
                                    <option key={year} value={year}>{year}</option>
                                ))}
                            </select>
                        </div>
                        <div className="h-48 md:h-64 w-full relative">
                            <div className="absolute inset-0">
                                <ResponsiveContainer width="99%" height="100%">
                                    <BarChart data={spendingData}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                        <XAxis dataKey="name" stroke="#9ca3af" fontSize={12} tickLine={false} axisLine={false} />
                                        <YAxis
                                            stroke="#9ca3af"
                                            fontSize={12}
                                            tickLine={false}
                                            axisLine={false}
                                            width={80}
                                            tickFormatter={(value) => {
                                                if (value >= 1000000) return `${(value / 1000000).toLocaleString('de-DE', { maximumFractionDigits: 1 })} Mio. €`;
                                                if (value >= 1000) return `${(value / 1000).toLocaleString('de-DE', { maximumFractionDigits: 0 })} Tsd. €`;
                                                return `${value.toLocaleString('de-DE')} €`;
                                            }}
                                        />
                                        <RechartsTooltip
                                            cursor={{ fill: '#374151', opacity: 0.5 }}
                                            contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '0.5rem', color: '#fff' }}
                                            itemStyle={{ color: '#fff' }}
                                            labelStyle={{ color: '#fff' }}
                                            formatter={(value: number) => [value.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' }), 'Betrag']}
                                        />
                                        <Bar dataKey="amount" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                                    </BarChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    </div>
                    {/* Donut Chart Section */}
                    <div className="flex-1 min-w-0 border-t md:border-t-0 md:border-l border-gray-700 pt-4 md:pt-0 md:pl-4">
                        <p className="text-xs text-gray-400 mb-2">Kostenverteilung</p>
                        <div className="h-48 md:h-64 w-full relative">
                            <div className="absolute inset-0">
                                <ResponsiveContainer width="99%" height="100%">
                                    <PieChart>
                                        <Pie
                                            data={costDistributionData}
                                            cx="50%"
                                            cy="50%"
                                            innerRadius={40}
                                            outerRadius={60}
                                            paddingAngle={5}
                                            dataKey="value"
                                        >
                                            {costDistributionData.map((entry, index) => (
                                                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                            ))}
                                        </Pie>
                                        <RechartsTooltip
                                            contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '0.5rem', color: '#fff', maxWidth: '300px' }}
                                            itemStyle={{ color: '#fff', whiteSpace: 'normal', wordWrap: 'break-word' }}
                                            labelStyle={{ display: 'none' }}
                                            formatter={(value: number, name: string) => {
                                                const percent = totalValue > 0 ? (value / totalValue * 100) : 0;
                                                // Truncate very long names for tooltip
                                                const displayName = name.length > 50 ? name.substring(0, 47) + '...' : name;
                                                return [`${percent.toLocaleString('de-DE', { maximumFractionDigits: 1 })}%`, displayName];
                                            }}
                                        />
                                    </PieChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Contract List */}
            <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
                {contracts?.map((contract) => (
                    <div key={contract.id} className={`bg-gray-800 border ${contract.is_protected ? 'border-green-800' : 'border-gray-700'} rounded-xl p-6 hover:border-gray-600 transition-all group relative hover:-translate-y-1 hover:shadow-xl`}>
                        {contract.is_protected && (
                            <div className="absolute top-0 right-0 p-2 bg-green-900/80 text-green-200 text-xs font-bold rounded-bl-lg rounded-tr-xl flex items-center gap-1">
                                <FiShield size={12} /> GESCHÜTZT
                            </div>
                        )}
                        <div className="flex justify-between items-start mb-4">
                            <div className="p-3 bg-blue-500/10 rounded-lg text-blue-400 group-hover:bg-blue-500/20 transition-colors">
                                <FiCalendar size={24} />
                            </div>
                            <div className="flex gap-2">
                                <span className={`text-xs font-medium px-2 py-1 rounded ${getStatusClass(contract.end_date)}`}>
                                    {getStatusLabel(contract.end_date)}
                                </span>
                                <button
                                    onClick={() => {
                                        setAuditContract({ id: contract.id, title: contract.title });
                                        setIsAuditOpen(true);
                                    }}
                                    className="p-1 px-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-xs transition-colors"
                                >
                                    Ansicht
                                </button>
                                {contract.can_write && (
                                    <button
                                        onClick={() => {
                                            setEditingContract(contract);
                                            setIsUploadOpen(true);
                                        }}
                                        className="p-1 px-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-xs transition-colors"
                                    >
                                        Bearbeiten
                                    </button>
                                )}
                                {contract.can_delete && (
                                    <button
                                    onClick={() => handleDelete(contract.id, contract.title, contract.is_protected)}
                                    className={`p-1 px-2 rounded text-xs transition-colors ${contract.is_protected ? 'bg-gray-700 text-gray-500 cursor-not-allowed' : 'bg-red-900/30 hover:bg-red-900/50 text-red-400'}`}
                                    title={contract.is_protected ? "Geschützt (In 'Geschützt' entsperren)" : "Löschen"}
                                    disabled={contract.is_protected}
                                >
                                    <FiTrash2 />
                                </button>
                                )}
                            </div>
                        </div>

                        <h3 className="text-lg font-semibold text-white mb-1 flex items-center gap-2">
                            {contract.is_protected && <FiShield className="text-green-500" size={16} />}
                            {contract.title}
                        </h3>

                        {/* Tags */}
                        <div className="flex flex-wrap gap-2 mb-3">
                            {contract.tags?.map((tag, i) => (
                                <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-gray-700 text-gray-300 border border-gray-600">#{tag.name}</span>
                            ))}
                            {contract.lists?.map((list, i) => (
                                <span key={`list-${i}`} className="text-[10px] px-2 py-0.5 rounded-full text-white border" style={{ backgroundColor: `${list.color}30`, borderColor: list.color, color: list.color }}>{list.name}</span>
                            ))}
                        </div>

                        <p className="text-sm text-gray-400 mb-4 line-clamp-2 h-10">{contract.description || "Keine Beschreibung vorhanden."}</p>

                        <div className="flex justify-between items-center text-xs text-gray-500 mb-6 border-t border-gray-700/50 pt-4">
                            <div className="flex items-center gap-1">
                                <FiClock />
                                <span>{formatContractDate(contract.start_date)}</span>
                            </div>
                            <div className="flex items-center gap-1 font-bold text-gray-400">
                                <span>€</span>
                                <span>{contract.value != null ? formatGermanNumber(contract.value) : '-'}</span>
                            </div>
                        </div>

                        <div className="flex gap-2">
                            <button
                                onClick={() => handleDownload(contract.id, contract.title, contract.file_extension)}
                                className="flex-1 flex items-center justify-center gap-2 bg-gray-700 hover:bg-gray-600 text-gray-200 py-2 rounded-lg transition-colors text-sm"
                            >
                                <FiDownload />
                                <span>PDF</span>
                            </button>
                            <button className="px-3 bg-gray-700 hover:bg-gray-600 rounded-lg text-gray-400 hover:text-white transition-colors">
                                v{contract.version || 1}
                            </button>
                            {contract.can_manage_protection && (
                                <button
                                onClick={() => handleToggleProtection(contract.id, contract.is_protected, contract.title)}
                                className={`px-3 rounded-lg transition-colors ${contract.is_protected ? 'bg-green-900/30 hover:bg-green-900/50 text-green-400' : 'bg-gray-700 hover:bg-gray-600 text-gray-400 hover:text-white'}`}
                                title={contract.is_protected ? "Schutz aufheben" : "Schützen"}
                            >
                                {contract.is_protected ? <FiShield /> : <FiLock />}
                            </button>
                            )}
                            {isAdmin && (
                                <button
                                    onClick={() => {
                                        setAddToListContract({ id: contract.id, title: contract.title });
                                        setIsAddToListOpen(true);
                                    }}
                                    className="px-3 bg-indigo-900/30 hover:bg-indigo-900/50 rounded-lg text-indigo-400 hover:text-indigo-300 transition-colors"
                                    title="Zu Liste hinzufügen"
                                >
                                    <FiFolder />
                                </button>
                            )}
                        </div>
                    </div>
                ))}
            </div>

            <UploadModal
                isOpen={isUploadOpen}
                onClose={() => {
                    setIsUploadOpen(false);
                    setEditingContract(null);
                }}
                initialData={editingContract}
            />
            <AuditModal
                isOpen={isAuditOpen}
                onClose={() => setIsAuditOpen(false)}
                contractId={auditContract?.id || null}
                contractTitle={auditContract?.title || ''}
            />
            <AddToListModal
                isOpen={isAddToListOpen}
                onClose={() => {
                    setIsAddToListOpen(false);
                    setAddToListContract(null);
                }}
                contractId={addToListContract?.id || null}
                contractTitle={addToListContract?.title || ''}
            />
        </div>
    )
}

export default Dashboard
