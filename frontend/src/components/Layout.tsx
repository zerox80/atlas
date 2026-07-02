import React from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { FiLogOut, FiFileText, FiPieChart, FiMenu, FiX, FiShield, FiFolder, FiCalendar } from 'react-icons/fi'
import { useUser } from '../App'
import api from '../api'

interface LayoutProps {
    children: React.ReactNode
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
    const navigate = useNavigate()
    const [isMobileMenuOpen, setIsMobileMenuOpen] = React.useState(false)
    const { isAdmin } = useUser()

    const handleLogout = async () => {
        try {
            await api.post('/logout')
        } catch {
            // Ignore errors
        }
        navigate('/login')
        window.location.reload()
    }

    return (
        <div className="flex h-screen bg-gray-900 text-white overflow-hidden">
            {/* Mobile Header */}
            <div className="md:hidden fixed top-0 left-0 right-0 h-16 bg-gray-800 border-b border-gray-700 flex items-center px-4 z-40">
                <button
                    onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
                    className="p-2 rounded hover:bg-gray-700 text-gray-300"
                >
                    {isMobileMenuOpen ? <FiX size={24} /> : <FiMenu size={24} />}
                </button>
                <span className="ml-4 text-xl font-bold text-blue-500">ZE Dashboard</span>
            </div>

            {/* Mobile Overlay */}
            {isMobileMenuOpen && (
                <div
                    className="fixed inset-0 bg-black/50 z-30 md:hidden"
                    onClick={() => setIsMobileMenuOpen(false)}
                />
            )}

            {/* Sidebar */}
            <div className={`
                fixed inset-y-0 left-0 z-50 w-64 bg-gray-800 border-r border-gray-700 p-4 flex flex-col transition-transform duration-300 ease-in-out
                md:relative md:translate-x-0
                ${isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}
            `}>
                <div className="text-2xl font-bold mb-8 text-blue-500 hidden md:block">ZE Dashboard</div>

                {/* Mobile Close Button (Optional, nicely integrated in header but good to have inside too if header is separate) */}
                <div className="md:hidden flex justify-between items-center mb-8">
                    <span className="text-xl font-bold text-blue-500">Menu</span>
                    <button onClick={() => setIsMobileMenuOpen(false)} className="p-2 hover:bg-gray-700 rounded"><FiX size={20} /></button>
                </div>

                <nav className="flex-1 space-y-2">
                    <Link
                        to="/"
                        onClick={() => setIsMobileMenuOpen(false)}
                        className="flex items-center space-x-2 p-3 rounded hover:bg-gray-700 transition-colors text-gray-300 hover:text-white"
                    >
                        <FiPieChart />
                        <span>Dashboard</span>
                    </Link>
                    <Link
                        to="/calendar"
                        onClick={() => setIsMobileMenuOpen(false)}
                        className="flex items-center space-x-2 p-3 rounded hover:bg-gray-700 transition-colors text-gray-300 hover:text-white"
                    >
                        <FiCalendar />
                        <span>Kalender</span>
                    </Link>
                    <Link
                        to="/contracts"
                        onClick={() => setIsMobileMenuOpen(false)}
                        className="flex items-center space-x-2 p-3 rounded hover:bg-gray-700 transition-colors text-gray-300 hover:text-white"
                    >
                        <FiFileText />
                        <span>Verträge</span>
                    </Link>
                    <Link
                        to="/lists"
                        onClick={() => setIsMobileMenuOpen(false)}
                        className="flex items-center space-x-2 p-3 rounded hover:bg-gray-700 transition-colors text-gray-300 hover:text-white"
                    >
                        <FiFolder />
                        <span>Listen</span>
                    </Link>
                    <Link
                        to="/protected"
                        onClick={() => setIsMobileMenuOpen(false)}
                        className="flex items-center space-x-2 p-3 rounded hover:bg-gray-700 transition-colors text-gray-300 hover:text-white"
                    >
                        <FiShield />
                        <span>Geschützt</span>
                    </Link>
                    {/* Admin Link - only visible for admins */}
                    {isAdmin && (
                        <Link
                            to="/admin"
                            onClick={() => setIsMobileMenuOpen(false)}
                            className="flex items-center space-x-2 p-3 rounded hover:bg-purple-900/50 transition-colors text-purple-400 hover:text-purple-300"
                        >
                            <FiShield />
                            <span>Admin</span>
                        </Link>
                    )}
                </nav>
                <button onClick={handleLogout} className="flex items-center space-x-2 p-3 rounded hover:bg-red-900/50 text-red-400 hover:text-red-300 transition-colors mt-auto">
                    <FiLogOut />
                    <span>Logout</span>
                </button>
            </div>

            {/* Main Content */}
            <div className="flex-1 overflow-auto p-4 md:p-8 pt-20 md:pt-8">
                {children}
            </div>
        </div>
    )
}

export default Layout

