import React, { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
    format,
    startOfMonth,
    endOfMonth,
    startOfWeek,
    endOfWeek,
    eachDayOfInterval,
    isSameMonth,
    isSameDay,
    addMonths,
    subMonths,
    isToday,
    parseISO,
    subDays
} from 'date-fns'
import { de } from 'date-fns/locale'
import { FiChevronLeft, FiChevronRight } from 'react-icons/fi'
import api from '../api'
import { Contract } from '../types'

import UploadModal from '../components/UploadModal'

const Calendar: React.FC = () => {
    const [currentDate, setCurrentDate] = useState(new Date())
    const [selectedContract, setSelectedContract] = useState<Contract | null>(null)
    const [isModalOpen, setIsModalOpen] = useState(false)

    // Fetch all active contracts (we filter client-side for now)
    const { data: contracts, isLoading } = useQuery<Contract[]>(['contracts', 'all'], async () => {
        const res = await api.get('/contracts?status=active')
        return res.data
    })

    const days = useMemo(() => {
        const monthStart = startOfMonth(currentDate)
        const monthEnd = endOfMonth(monthStart)
        const startDate = startOfWeek(monthStart, { weekStartsOn: 1 }) // Monday start
        const endDate = endOfWeek(monthEnd, { weekStartsOn: 1 })

        return eachDayOfInterval({
            start: startDate,
            end: endDate
        })
    }, [currentDate])

    const nextMonth = () => setCurrentDate(addMonths(currentDate, 1))
    const prevMonth = () => setCurrentDate(subMonths(currentDate, 1))
    const jumpToToday = () => setCurrentDate(new Date())

    const getEventsForDay = (day: Date) => {
        if (!contracts) return []

        interface CalendarEvent {
            type: 'start' | 'end' | 'notice';
            color: string;
            label: string;
            contract: Contract;
        }

        const events: CalendarEvent[] = []

        contracts.forEach(contract => {
            // Start Date (Green)
            if (contract.start_date && isSameDay(parseISO(contract.start_date), day)) {
                events.push({
                    type: 'start',
                    color: 'bg-green-500',
                    label: 'Start',
                    contract
                })
            }

            // End Date (Red)
            if (contract.end_date && isSameDay(parseISO(contract.end_date), day)) {
                events.push({
                    type: 'end',
                    color: 'bg-red-500',
                    label: 'Ende',
                    contract
                })
            }

            // Notice Deadline (Yellow)
            if (contract.end_date && contract.notice_period) {
                const deadline = subDays(parseISO(contract.end_date), contract.notice_period)
                if (isSameDay(deadline, day)) {
                    events.push({
                        type: 'notice',
                        color: 'bg-yellow-500',
                        label: `Kündigungsfrist`,
                        contract
                    })
                }
            }
        })

        return events
    }

    const weekDays = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

    if (isLoading) return <div className="p-8 text-center text-gray-400">Lade Kalender...</div>

    return (
        <div className="p-6 max-w-7xl mx-auto">
            {/* Header */}
            <div className="flex flex-col md:flex-row justify-between items-center mb-8 gap-4">
                <div>
                    <h1 className="text-3xl font-bold text-white mb-2">Kalender</h1>
                    <p className="text-gray-400">Behalten Sie alle Fristen im Blick.</p>
                </div>

                <div className="flex items-center gap-4 bg-gray-800 p-2 rounded-xl border border-gray-700">
                    <button onClick={prevMonth} className="p-2 hover:bg-gray-700 rounded-lg text-gray-300 transition-colors">
                        <FiChevronLeft size={20} />
                    </button>
                    <div className="text-lg font-semibold text-white min-w-[140px] text-center">
                        {format(currentDate, 'MMMM yyyy', { locale: de })}
                    </div>
                    <button onClick={nextMonth} className="p-2 hover:bg-gray-700 rounded-lg text-gray-300 transition-colors">
                        <FiChevronRight size={20} />
                    </button>
                    <button onClick={jumpToToday} className="ml-2 px-3 py-1 text-sm bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors">
                        Heute
                    </button>
                </div>
            </div>

            {/* Grid */}
            <div className="bg-gray-800 border border-gray-700 rounded-2xl shadow-xl overflow-hidden">
                {/* Weekday Headers */}
                <div className="grid grid-cols-7 border-b border-gray-700 bg-gray-800/50">
                    {weekDays.map(day => (
                        <div key={day} className="py-3 text-center text-sm font-medium text-gray-400">
                            {day}
                        </div>
                    ))}
                </div>

                {/* Days */}
                <div className="grid grid-cols-7 auto-rows-fr bg-gray-900">
                    {days.map((day) => {
                        const events = getEventsForDay(day)
                        const isCurrentMonth = isSameMonth(day, currentDate)
                        const isTodayDate = isToday(day)

                        return (
                            <div
                                key={day.toISOString()}
                                className={`min-h-[120px] border-b border-r border-gray-800 p-2 transition-colors hover:bg-gray-800/30 ${!isCurrentMonth ? 'bg-gray-900/50 opacity-50' : ''
                                    } ${isTodayDate ? 'bg-blue-900/10' : ''}`}
                            >
                                <div className="flex justify-between items-start mb-2">
                                    <span className={`text-sm font-medium h-7 w-7 flex items-center justify-center rounded-full ${isTodayDate
                                        ? 'bg-blue-600 text-white'
                                        : isCurrentMonth ? 'text-gray-300' : 'text-gray-600'
                                        }`}>
                                        {format(day, 'd')}
                                    </span>
                                </div>

                                <div className="space-y-1">
                                    {events.map((event, i) => (
                                        <div
                                            key={i}
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                setSelectedContract(event.contract);
                                                setIsModalOpen(true);
                                            }}
                                            className={`text-xs px-2 py-1 rounded truncate cursor-pointer group relative ${event.color} text-white bg-opacity-80 hover:bg-opacity-100 transition-opacity`}
                                        >
                                            <span className="font-bold mr-1">{event.label}:</span>
                                            {event.contract.title}

                                            {/* Tooltip */}
                                            <div className="absolute left-0 bottom-full mb-2 hidden group-hover:block z-50 w-64 p-3 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl text-left pointer-events-none">
                                                <div className="font-bold text-white mb-1">{event.contract.title}</div>
                                                <div className="text-gray-400 text-xs mb-2">{event.contract.description?.substring(0, 50)}...</div>
                                                <div className="grid grid-cols-2 gap-2 text-xs">
                                                    <span className="text-gray-500">Event:</span>
                                                    <span className="text-white">{event.label}</span>
                                                    <span className="text-gray-500">Datum:</span>
                                                    <span className="text-white">{format(day, 'dd.MM.yyyy')}</span>
                                                    <span className="text-gray-500">Wert:</span>
                                                    <span className="text-white">{event.contract.value} €</span>
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )
                    })}
                </div>
            </div>

            <UploadModal
                isOpen={isModalOpen}
                onClose={() => {
                    setIsModalOpen(false)
                    setSelectedContract(null)
                }}
                initialData={selectedContract}
            />

            {/* Legend */}
            <div className="flex gap-6 mt-6 justify-center text-sm text-gray-400">
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-green-500" /> Vertragsbeginn
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-red-500" /> Vertragsende
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-yellow-500" /> Kündigungsfrist
                </div>
            </div>
        </div>
    )
}

export default Calendar
