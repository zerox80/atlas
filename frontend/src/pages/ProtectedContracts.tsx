import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FiAlertCircle, FiArrowUpRight, FiLock, FiShield, FiUnlock } from 'react-icons/fi'
import api, { toggleContractProtection } from '../api'
import { Contract } from '../types'
import { EmptyState, LoadingState, PageHeader } from '../components/ui'

const money = (value?: number | null) => value == null ? '–' : value.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })

const ProtectedContracts: React.FC = () => {
    const [contracts, setContracts] = useState<Contract[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const navigate = useNavigate()

    const fetchProtectedContracts = async () => {
        setIsLoading(true)
        try {
            const response = await api.get<Contract[]>('/contracts')
            setContracts(response.data.filter((contract) => contract.is_protected))
            setError(null)
        } catch {
            setError('Geschützte Dokumente konnten nicht geladen werden.')
        } finally {
            setIsLoading(false)
        }
    }

    useEffect(() => { fetchProtectedContracts() }, [])

    const handleUnprotect = async (contract: Contract) => {
        if (!window.confirm(`Schutz für „${contract.title}“ wirklich aufheben?`)) return
        try {
            await toggleContractProtection(contract.id)
            fetchProtectedContracts()
        } catch {
            alert('Der Schutzstatus konnte nicht geändert werden.')
        }
    }

    if (isLoading) return <LoadingState label="Geschützte Dokumente werden geladen" />

    return <div className="app-page">
        <PageHeader
            eyebrow="Security / Vault"
            title="Protected Vault"
            description="Ein kontrollierter Bereich für Dokumente mit Löschschutz und erhöhten Zugriffsanforderungen."
            actions={<span className="chip border-emerald-300/20 bg-emerald-300/[0.07] text-emerald-200"><FiShield /> {contracts.length} geschützt</span>}
        />

        <section className="mb-5 flex gap-4 rounded-3xl border border-[#7397ff]/15 bg-[#7397ff]/[0.045] p-5">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[#7397ff]/10 text-[#9ab1ff]"><FiAlertCircle /></div>
            <div><h2 className="text-sm font-semibold">Löschschutz ist aktiv</h2><p className="mt-1 max-w-3xl text-sm leading-6 text-white/43">Geschützte Dokumente können nicht gelöscht werden. Berechtigte Nutzer müssen den Schutz hier bewusst aufheben, bevor eine Löschung möglich wird.</p></div>
        </section>

        {error && <div className="mb-5 rounded-2xl border border-rose-400/20 bg-rose-400/[0.07] px-4 py-3 text-sm text-rose-200">{error}</div>}

        {contracts.length ? <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {contracts.map((contract) => <article key={contract.id} className="surface-interactive group relative overflow-hidden p-6">
                <div className="absolute right-4 top-4 flex h-9 w-9 items-center justify-center rounded-2xl border border-emerald-300/15 bg-emerald-300/[0.07] text-emerald-200"><FiLock /></div>
                <p className="eyebrow">{contract.document_type === 'invoice' ? 'Protected invoice' : 'Protected contract'}</p>
                <h2 className="mt-3 max-w-[82%] truncate text-xl font-semibold tracking-[-0.025em]">{contract.title}</h2>
                <p className="mt-2 min-h-10 line-clamp-2 text-sm leading-5 text-white/40">{contract.description || 'Keine Beschreibung hinterlegt.'}</p>
                <div className="my-5 h-px bg-white/[0.07]" />
                <dl className="grid grid-cols-2 gap-4">
                    <div><dt className="eyebrow">Wert</dt><dd className="mt-2 text-sm font-semibold">{money(contract.value)}</dd></div>
                    <div><dt className="eyebrow">Laufzeitende</dt><dd className="mt-2 text-sm font-semibold">{contract.end_date ? new Date(contract.end_date).toLocaleDateString('de-DE') : 'Unbefristet'}</dd></div>
                </dl>
                <div className="mt-6">
                    {contract.can_manage_protection ? <button onClick={() => handleUnprotect(contract)} className="btn-secondary w-full hover:border-rose-300/25 hover:text-rose-200"><FiUnlock /> Schutz aufheben</button> : <div className="rounded-xl border border-white/[0.07] bg-black/20 px-3 py-2 text-center text-xs text-white/32">Vollzugriff zum Entsperren erforderlich</div>}
                </div>
            </article>)}
        </section> : <EmptyState icon={FiShield} title="Der Vault ist leer" description="Aktuell ist kein Dokument mit Löschschutz versehen." action={<button onClick={() => navigate('/contracts')} className="btn-secondary">Zu den Verträgen <FiArrowUpRight /></button>} />}
    </div>
}

export default ProtectedContracts
