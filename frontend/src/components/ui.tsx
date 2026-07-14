import type React from 'react'
import type { IconType } from 'react-icons'
import { FiArrowUpRight, FiInbox } from 'react-icons/fi'

export const PageHeader = ({ eyebrow, title, description, actions }: {
    eyebrow: string
    title: string
    description: string
    actions?: React.ReactNode
}) => (
    <header className="mb-7 flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
            <p className="eyebrow">{eyebrow}</p>
            <h1 className="page-title">{title}</h1>
            <p className="page-subtitle">{description}</p>
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
)

export const LoadingState = ({ label = 'Daten werden geladen' }: { label?: string }) => (
    <div className="app-page">
        <div className="mb-8 h-4 w-28 skeleton" />
        <div className="mb-3 h-10 w-72 max-w-full skeleton" />
        <div className="mb-8 h-5 w-[430px] max-w-full skeleton" />
        <div className="grid gap-4 md:grid-cols-3">
            {[0, 1, 2].map((item) => <div key={item} className="h-40 skeleton" />)}
        </div>
        <span className="sr-only">{label}</span>
    </div>
)

export const EmptyState = ({ icon: Icon = FiInbox, title, description, action }: {
    icon?: IconType
    title: string
    description: string
    action?: React.ReactNode
}) => (
    <div className="surface flex min-h-64 flex-col items-center justify-center px-6 py-12 text-center">
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl border border-[#b8f15a]/20 bg-[#b8f15a]/[0.08] text-[#b8f15a]"><Icon size={22} /></div>
        <h2 className="section-title">{title}</h2>
        <p className="mt-2 max-w-md text-sm leading-6 muted">{description}</p>
        {action && <div className="mt-5">{action}</div>}
    </div>
)

export const MetricCard = ({ icon: Icon, label, value, meta, tone = 'lime' }: {
    icon: IconType
    label: string
    value: string | number
    meta: string
    tone?: 'lime' | 'blue' | 'violet' | 'amber'
}) => {
    const tones = {
        lime: 'bg-[#b8f15a]/10 text-[#b8f15a] border-[#b8f15a]/15',
        blue: 'bg-[#77a7ff]/10 text-[#77a7ff] border-[#77a7ff]/15',
        violet: 'bg-[#b28cff]/10 text-[#b28cff] border-[#b28cff]/15',
        amber: 'bg-amber-400/10 text-amber-300 border-amber-300/15',
    }
    return (
        <article className="surface surface-interactive p-5">
            <div className="mb-7 flex items-start justify-between">
                <div className={`flex h-10 w-10 items-center justify-center rounded-xl border ${tones[tone]}`}><Icon size={18} /></div>
                <FiArrowUpRight className="text-[#4f5968]" />
            </div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] muted">{label}</p>
            <p className="metric-value mt-2">{value}</p>
            <p className="mt-2 text-xs muted">{meta}</p>
        </article>
    )
}
