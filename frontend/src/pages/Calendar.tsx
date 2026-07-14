import React, { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { addMonths, eachDayOfInterval, endOfMonth, endOfWeek, format, isSameDay, isSameMonth, isToday, parseISO, startOfMonth, startOfWeek, subDays, subMonths } from 'date-fns'
import { de } from 'date-fns/locale'
import { FiCalendar, FiChevronLeft, FiChevronRight, FiClock } from 'react-icons/fi'
import api from '../api'
import { Contract } from '../types'
import UploadModal from '../components/UploadModal'
import { EmptyState, LoadingState, PageHeader } from '../components/ui'

interface CalendarEvent {
    type: 'start' | 'end' | 'notice'
    label: string
    contract: Contract
}

const eventStyle: Record<CalendarEvent['type'], string> = {
    start: 'border-emerald-400/20 bg-emerald-400/[0.09] text-emerald-200',
    end: 'border-rose-400/20 bg-rose-400/[0.09] text-rose-200',
    notice: 'border-amber-300/20 bg-amber-300/[0.09] text-amber-100',
}

const Calendar: React.FC = () => {
    const [currentDate, setCurrentDate] = useState(new Date())
    const [selectedContract, setSelectedContract] = useState<Contract | null>(null)
    const { data: contracts = [], isLoading } = useQuery<Contract[]>(['contracts', 'all'], async () => (await api.get('/contracts?status=active')).data)

    const days = useMemo(() => {
        const monthStart = startOfMonth(currentDate)
        return eachDayOfInterval({
            start: startOfWeek(monthStart, { weekStartsOn: 1 }),
            end: endOfWeek(endOfMonth(monthStart), { weekStartsOn: 1 }),
        })
    }, [currentDate])

    const getEventsForDay = (day: Date): CalendarEvent[] => contracts.flatMap((contract) => {
        const events: CalendarEvent[] = []
        if (contract.start_date && isSameDay(parseISO(contract.start_date), day)) events.push({ type: 'start', label: 'Start', contract })
        if (contract.end_date && isSameDay(parseISO(contract.end_date), day)) events.push({ type: 'end', label: 'Ende', contract })
        if (contract.end_date && isSameDay(subDays(parseISO(contract.end_date), contract.notice_period ?? 30), day)) events.push({ type: 'notice', label: 'Kündigen', contract })
        return events
    })

    const monthEvents = useMemo(() => days.flatMap(getEventsForDay), [days, contracts])
    const weekDays = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

    if (isLoading) return <LoadingState label="Kalender wird geladen" />

    return <div className="app-page">
        <PageHeader
            eyebrow="Operations / Timeline"
            title="Fristenkalender"
            description="Vertragsstarts, Laufzeitenden und Kündigungsfenster in einer operativen Monatsansicht."
            actions={<div className="surface flex items-center gap-1 p-1.5">
                <button onClick={() => setCurrentDate(subMonths(currentDate, 1))} className="icon-btn border-transparent"><FiChevronLeft /></button>
                <div className="min-w-36 px-2 text-center text-sm font-semibold capitalize">{format(currentDate, 'MMMM yyyy', { locale: de })}</div>
                <button onClick={() => setCurrentDate(addMonths(currentDate, 1))} className="icon-btn border-transparent"><FiChevronRight /></button>
                <button onClick={() => setCurrentDate(new Date())} className="btn-secondary ml-1 h-9 px-3">Heute</button>
            </div>}
        />

        <section className="mb-4 flex flex-wrap gap-2">
            {[['start', 'Vertragsbeginn'], ['notice', 'Kündigungsfrist'], ['end', 'Vertragsende']].map(([type, label]) => <span key={type} className={`chip border ${eventStyle[type as CalendarEvent['type']]}`}>{label} · {monthEvents.filter((event) => event.type === type).length}</span>)}
        </section>

        {contracts.length ? <section className="surface overflow-hidden">
            <div className="grid grid-cols-7 border-b border-white/[0.07] bg-white/[0.015]">
                {weekDays.map((day) => <div key={day} className="py-3 text-center text-[10px] font-bold uppercase tracking-[0.16em] text-white/32">{day}</div>)}
            </div>
            <div className="grid grid-cols-7">
                {days.map((day) => {
                    const events = getEventsForDay(day)
                    const currentMonth = isSameMonth(day, currentDate)
                    return <div key={day.toISOString()} className={`group min-h-28 border-b border-r border-white/[0.055] p-1.5 transition-colors sm:min-h-32 sm:p-2 ${currentMonth ? 'hover:bg-white/[0.025]' : 'bg-black/20 opacity-38'} ${isToday(day) ? 'bg-[#b8f15a]/[0.035]' : ''}`}>
                        <span className={`flex h-7 w-7 items-center justify-center rounded-xl text-xs font-semibold ${isToday(day) ? 'bg-[#b8f15a] text-[#11150b]' : 'text-white/52'}`}>{format(day, 'd')}</span>
                        <div className="mt-1.5 space-y-1">
                            {events.slice(0, 3).map((event) => <button key={`${event.type}-${event.contract.id}`} onClick={() => setSelectedContract(event.contract)} title={`${event.label}: ${event.contract.title}`} className={`block w-full truncate rounded-lg border px-1.5 py-1 text-left text-[10px] font-semibold sm:px-2 sm:text-xs ${eventStyle[event.type]}`}>
                                <span className="hidden sm:inline">{event.label} · </span>{event.contract.title}
                            </button>)}
                            {events.length > 3 && <p className="px-1 text-[10px] text-white/35">+{events.length - 3} weitere</p>}
                        </div>
                    </div>
                })}
            </div>
        </section> : <EmptyState icon={FiCalendar} title="Noch keine Termine" description="Sobald Verträge mit Laufzeit oder Kündigungsfrist vorhanden sind, entsteht hier automatisch deine Timeline." />}

        <div className="mt-4 flex items-center gap-2 text-xs text-white/32"><FiClock /> Termine werden direkt aus den Dokumentdaten berechnet.</div>
        <UploadModal isOpen={Boolean(selectedContract)} onClose={() => setSelectedContract(null)} initialData={selectedContract} />
    </div>
}

export default Calendar
