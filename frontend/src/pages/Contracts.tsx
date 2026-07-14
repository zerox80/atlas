import React, { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FiPlus, FiDownload, FiCalendar, FiClock, FiTrash2, FiAlertTriangle, FiCheckCircle, FiAlertOctagon, FiMessageCircle } from 'react-icons/fi'
import api from '../api'
import UploadModal from '../components/UploadModal'
import ContractChat from '../components/ContractChat'
import { motion } from 'framer-motion'

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
    version?: number
    notice_period?: number | null
    file_extension: string
    document_type: 'contract' | 'invoice'
    is_protected: boolean
    can_read: boolean
    can_write: boolean
    can_delete: boolean
    can_manage_protection: boolean
}

const DEFAULT_NOTICE_PERIOD = 30

const isPdfContract = (contract: Contract) => contract.file_extension.toLowerCase() === '.pdf'

const Contracts: React.FC = () => {
    const [isUploadOpen, setIsUploadOpen] = useState(false)
    const [editingContract, setEditingContract] = useState<Contract | null>(null)
    const [chatContract, setChatContract] = useState<Contract | null>(null)
    const queryClient = useQueryClient()

    const { data: contracts, isLoading } = useQuery<Contract[]>(['contracts'], async () => {
        const res = await api.get('/contracts', { params: { document_type: 'contract' } })
        return res.data
    })

    const handleDelete = async (id: number, title: string, isProtected: boolean) => {
        if (isProtected) {
            alert('Dieser Vertrag ist geschuetzt. Bitte heben Sie zuerst den Schutz auf.');
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

    const getStatusColor = (endDate?: string, noticePeriod?: number) => {
        if (!endDate) return { color: 'bg-emerald-900/10 border-emerald-500/30', text: 'text-emerald-400', status: 'Unbefristet', icon: <FiCheckCircle /> }; // No end date
        
        const end = new Date(endDate);
        const cancellationDeadline = new Date(end);
        cancellationDeadline.setDate(end.getDate() - (noticePeriod ?? DEFAULT_NOTICE_PERIOD));

        const now = new Date();
        const daysToDeadline = Math.ceil((cancellationDeadline.getTime() - now.getTime()) / (1000 * 3600 * 24));

        if (end < now) return { color: 'bg-gray-700 border-gray-600', text: 'text-gray-400', status: 'Abgelaufen', icon: <FiClock /> }; // Expired
        if (daysToDeadline < 0) return { color: 'bg-red-900/20 border-red-500/50', text: 'text-red-400', status: 'Verpasst', icon: <FiAlertOctagon /> }; // Deadline passed
        if (daysToDeadline <= 30) return { color: 'bg-amber-900/20 border-amber-500/50', text: 'text-amber-400', status: 'Bald Fällig', icon: <FiAlertTriangle /> }; // Warning
        return { color: 'bg-emerald-900/10 border-emerald-500/30', text: 'text-emerald-400', status: 'Aktiv', icon: <FiCheckCircle /> }; // Good
    }

    const getDeadlineText = (endDate?: string, noticePeriod?: number) => {
        if (!endDate) return "Unbefristeter Vertrag / Kein Enddatum";
        
        const end = new Date(endDate);
        const cancellationDeadline = new Date(end);
        cancellationDeadline.setDate(end.getDate() - (noticePeriod ?? DEFAULT_NOTICE_PERIOD));
        const now = new Date();

        if (end < now) return "Vertrag ist abgelaufen";

        const daysToDeadline = Math.ceil((cancellationDeadline.getTime() - now.getTime()) / (1000 * 3600 * 24));
        if (daysToDeadline < 0) return `Kündigungsfrist am ${cancellationDeadline.toLocaleDateString('de-DE')} abgelaufen`;
        return `Kündbar bis: ${cancellationDeadline.toLocaleDateString('de-DE')} (${daysToDeadline} Tage)`;
    }

    if (isLoading) return <div className="p-8 text-center text-gray-400">Lade Verträge...</div>

    return (
        <div>
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-10">
                <div>
                    <h1 className="text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-500 mb-2">Verträge & Fristen</h1>
                    <p className="text-gray-400 text-lg">Behalten Sie Ihre Kündigungsfristen im Auge.</p>
                </div>
                <button
                    onClick={() => setIsUploadOpen(true)}
                    className="flex w-full md:w-auto justify-center items-center gap-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white px-6 py-3 rounded-xl font-bold transition-all shadow-lg hover:shadow-blue-500/25 transform hover:-translate-y-0.5"
                >
                    <FiPlus size={20} />
                    <span>Neuer Vertrag</span>
                </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-8">
                {contracts?.map((contract, index) => {
                    const style = getStatusColor(contract.end_date, contract.notice_period ?? DEFAULT_NOTICE_PERIOD);
                    return (
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: index * 0.1 }}
                            key={contract.id}
                            className={`relative backdrop-blur-md border rounded-2xl p-6 transition-all hover:shadow-2xl hover:-translate-y-1 group ${style.color}`}
                        >
                            <div className="absolute top-4 right-4 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                {isPdfContract(contract) && (
                                    <button
                                        onClick={() => setChatContract(contract)}
                                        className="p-2 bg-purple-900/50 hover:bg-purple-900 text-purple-300 rounded-lg transition-colors"
                                        title="Mit KI chatten"
                                    >
                                        <FiMessageCircle />
                                    </button>
                                )}
                                {contract.can_write && (
                                    <button
                                        onClick={() => { setEditingContract(contract); setIsUploadOpen(true); }}
                                        className="p-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg transition-colors"
                                    >
                                        Bearbeiten
                                    </button>
                                )}
                                {contract.can_delete && (
                                    <button
                                        onClick={() => handleDelete(contract.id, contract.title, contract.is_protected)}
                                        className={`p-2 rounded-lg transition-colors ${contract.is_protected ? 'bg-gray-800 text-gray-500 cursor-not-allowed' : 'bg-red-900/50 hover:bg-red-900 text-red-300'}`}
                                        disabled={contract.is_protected}
                                    >
                                        <FiTrash2 />
                                    </button>
                                )}
                            </div>

                            <div className="flex items-center gap-3 mb-4">
                                <div className={`p-3 rounded-xl bg-gray-800/50 ${style.text}`}>
                                    {style.icon}
                                </div>
                                <div>
                                    <span className={`text-xs font-bold uppercase tracking-wider ${style.text}`}>
                                        {style.status}
                                    </span>
                                    <h3 className="text-xl font-bold text-white leading-tight">{contract.title}</h3>
                                </div>
                            </div>

                            {/* Warning Helper */}
                            <div className="mb-6 p-3 bg-gray-800/40 rounded-lg border border-gray-700/50">
                                <p className={`text-sm font-medium ${style.text} flex items-center gap-2`}>
                                    <FiAlertTriangle className="shrink-0" />
                                    {getDeadlineText(contract.end_date, contract.notice_period ?? DEFAULT_NOTICE_PERIOD)}
                                </p>
                            </div>

                            <div className="space-y-3 mb-6">
                                <div className="flex justify-between text-sm">
                                    <div className="flex items-center gap-2 text-gray-400">
                                        <FiCalendar />
                                        <span>Laufzeit</span>
                                    </div>
                                    <span className="text-white font-medium">
                                        {contract.start_date ? new Date(contract.start_date).toLocaleDateString() : 'Unbekannt'} - {contract.end_date ? new Date(contract.end_date).toLocaleDateString() : 'Unbefristet'}
                                    </span>
                                </div>
                                <div className="flex justify-between text-sm">
                                    <div className="flex items-center gap-2 text-gray-400">
                                        <FiClock />
                                        <span>Kündigungsfrist</span>
                                    </div>
                                    <span className="text-white font-medium">{contract.notice_period ?? DEFAULT_NOTICE_PERIOD} Tage</span>
                                </div>
                                <div className="flex justify-between text-sm">
                                    <div className="flex items-center gap-2 text-gray-400">
                                        <span>€</span>
                                        <span>Gesamtwert</span>
                                    </div>
                                    <span className="text-white font-medium">{contract.value != null ? `${contract.value.toLocaleString('de-DE')} €` : 'N/A'}</span>
                                </div>
                                {contract.annual_value != null && (
                                    <div className="flex justify-between text-sm mt-1">
                                        <div className="flex items-center gap-2 text-gray-400">
                                            <span>€</span>
                                            <span>Jährlich</span>
                                        </div>
                                        <span className="text-white font-medium">{contract.annual_value.toLocaleString('de-DE')} €</span>
                                    </div>
                                )}
                            </div>

                            <div className="flex flex-wrap gap-2 mb-6">
                                {contract.tags?.map((tag, i) => (
                                    <span key={i} className="text-[10px] px-2 py-1 rounded-md bg-gray-800 text-gray-400 border border-gray-700">#{tag.name}</span>
                                ))}
                            </div>

                            <button
                                onClick={() => handleDownload(contract.id, contract.title, contract.file_extension)}
                                className="w-full flex items-center justify-center gap-2 bg-gray-800/80 hover:bg-gray-700 text-white py-3 rounded-xl transition-colors font-medium border border-gray-600 hover:border-gray-500"
                            >
                                <FiDownload />
                                <span>Dokument herunterladen</span>
                            </button>
                        </motion.div>
                    )
                })}
            </div>

            <UploadModal
                isOpen={isUploadOpen}
                onClose={() => {
                    setIsUploadOpen(false);
                    setEditingContract(null);
                }}
                initialData={editingContract}
            />

            {/* AI Contract Chat */}
            <ContractChat
                isOpen={!!chatContract}
                onClose={() => setChatContract(null)}
                contractId={chatContract?.id || 0}
                contractTitle={chatContract?.title || ''}
            />
        </div>
    )
}

export default Contracts
