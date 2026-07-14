import React, { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FiDownload, FiFileText, FiPlus, FiTrash2 } from 'react-icons/fi'
import api from '../api'
import UploadModal from '../components/UploadModal'
import { formatGermanNumber } from '../utils/formatUtils'
import type { Contract } from '../types'

const Invoices: React.FC = () => {
    const [isUploadOpen, setIsUploadOpen] = useState(false)
    const [editingInvoice, setEditingInvoice] = useState<Contract | null>(null)
    const queryClient = useQueryClient()

    const { data: invoices, isLoading } = useQuery<Contract[]>(['invoices'], async () => {
        const response = await api.get('/contracts', { params: { document_type: 'invoice' } })
        return response.data
    })

    const handleDelete = async (invoice: Contract) => {
        if (invoice.is_protected) {
            alert('Diese Rechnung ist geschützt. Bitte heben Sie zuerst den Schutz auf.')
            return
        }
        if (!window.confirm(`Möchten Sie die Rechnung "${invoice.title}" wirklich löschen?`)) return
        try {
            await api.delete(`/contracts/${invoice.id}`)
            queryClient.invalidateQueries(['invoices'])
            queryClient.invalidateQueries(['contracts'])
        } catch {
            alert('Fehler beim Löschen der Rechnung.')
        }
    }

    const handleDownload = async (invoice: Contract) => {
        try {
            const response = await api.get(`/contracts/${invoice.id}/download`, { responseType: 'blob' })
            const extension = invoice.file_extension?.startsWith('.') ? invoice.file_extension : `.${invoice.file_extension || 'pdf'}`
            const url = window.URL.createObjectURL(new Blob([response.data]))
            const link = document.createElement('a')
            link.href = url
            link.download = invoice.title.endsWith(extension) ? invoice.title : `${invoice.title}${extension}`
            document.body.appendChild(link)
            link.click()
            link.remove()
            window.URL.revokeObjectURL(url)
        } catch {
            alert('Fehler beim Herunterladen der Rechnung.')
        }
    }

    if (isLoading) return <div className="p-8 text-center text-gray-400">Lade Rechnungen...</div>

    return (
        <div>
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-10">
                <div>
                    <h1 className="text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-500 mb-2">Rechnungen</h1>
                    <p className="text-gray-400 text-lg">Rechnungen unabhängig von Verträgen hochladen und verwalten.</p>
                </div>
                <button
                    onClick={() => setIsUploadOpen(true)}
                    className="flex w-full md:w-auto justify-center items-center gap-2 bg-gradient-to-r from-emerald-600 to-cyan-600 hover:from-emerald-500 hover:to-cyan-500 text-white px-6 py-3 rounded-xl font-bold transition-all shadow-lg"
                >
                    <FiPlus size={20} />
                    <span>Neue Rechnung</span>
                </button>
            </div>

            {invoices?.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-gray-700 bg-gray-800/40 p-12 text-center text-gray-400">
                    Noch keine Rechnungen hochgeladen.
                </div>
            ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
                    {invoices?.map((invoice) => (
                        <article key={invoice.id} className="rounded-2xl border border-gray-700 bg-gray-800/60 p-6">
                            <div className="flex items-start justify-between gap-4 mb-4">
                                <div className="flex items-center gap-3 min-w-0">
                                    <div className="p-3 rounded-xl bg-emerald-500/10 text-emerald-400"><FiFileText size={22} /></div>
                                    <div className="min-w-0">
                                        <p className="text-xs font-bold uppercase tracking-wide text-emerald-400">Rechnung</p>
                                        <h2 className="truncate text-lg font-semibold text-white">{invoice.title}</h2>
                                    </div>
                                </div>
                                <div className="flex gap-2">
                                    {invoice.can_write && <button onClick={() => { setEditingInvoice(invoice); setIsUploadOpen(true) }} className="text-sm text-gray-300 hover:text-white">Bearbeiten</button>}
                                    {invoice.can_delete && <button onClick={() => handleDelete(invoice)} disabled={invoice.is_protected} className="text-red-400 hover:text-red-300 disabled:text-gray-600"><FiTrash2 /></button>}
                                </div>
                            </div>
                            <p className="h-10 text-sm text-gray-400 line-clamp-2">{invoice.description || 'Keine Beschreibung vorhanden.'}</p>
                            <div className="my-5 flex justify-between border-y border-gray-700 py-3 text-sm">
                                <span className="text-gray-400">Rechnungsdatum</span>
                                <span className="font-medium text-white">{invoice.start_date ? new Date(invoice.start_date).toLocaleDateString('de-DE') : '-'}</span>
                            </div>
                            <p className="mb-5 text-2xl font-bold text-emerald-400">{invoice.value != null ? `${formatGermanNumber(invoice.value)} €` : '-'}</p>
                            <div className="flex flex-wrap gap-2 mb-5">{invoice.tags.map((tag) => <span key={tag.name} className="rounded-full border border-gray-600 bg-gray-700 px-2 py-0.5 text-xs text-gray-300">#{tag.name}</span>)}</div>
                            <button onClick={() => handleDownload(invoice)} className="flex w-full items-center justify-center gap-2 rounded-xl bg-gray-700 py-2.5 text-sm text-white hover:bg-gray-600"><FiDownload /> Rechnung herunterladen</button>
                        </article>
                    ))}
                </div>
            )}

            <UploadModal
                isOpen={isUploadOpen}
                onClose={() => { setIsUploadOpen(false); setEditingInvoice(null) }}
                initialData={editingInvoice}
                documentType="invoice"
            />
        </div>
    )
}

export default Invoices
