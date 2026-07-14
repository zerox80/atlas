import { BrowserRouter as Router, Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Contracts from './pages/Contracts'
import Invoices from './pages/Invoices'
import AdminPanel from './pages/AdminPanel'
import Lists from './pages/Lists'
import Calendar from './pages/Calendar'
import ProtectedContracts from './pages/ProtectedContracts'
import Layout from './components/Layout'
import { useState, useEffect, createContext, useContext } from 'react'
import api from './api'

// User Context
interface UserInfo {
    id: number
    username: string
    role: string
    has_2fa: boolean
}

interface UserContextType {
    user: UserInfo | null
    setUser: (user: UserInfo | null) => void
    isAdmin: boolean
}

export const UserContext = createContext<UserContextType>({
    user: null,
    setUser: () => { },
    isAdmin: false
})

export const useUser = () => useContext(UserContext)

export function AppRoutes() {
    const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false)
    const [isLoading, setIsLoading] = useState<boolean>(true)
    const [user, setUser] = useState<UserInfo | null>(null)
    const navigate = useNavigate()

    useEffect(() => {
        const checkAuth = async () => {
            try {
                // First check if authenticated by calling /me
                const meRes = await api.get('/me')
                setUser(meRes.data)
                setIsAuthenticated(true)
            } catch {
                setIsAuthenticated(false)
                setUser(null)
            } finally {
                setIsLoading(false)
            }
        }
        checkAuth()
    }, [])

    const handleLoginSuccess = async () => {
        try {
            const meRes = await api.get('/me')
            setUser(meRes.data)
            setIsAuthenticated(true)
            navigate('/')
        } catch {
            console.error('Failed to get user info after login')
        }
    }

    if (isLoading) {
        return <div className="min-h-screen bg-gray-950 flex items-center justify-center text-white">Loading...</div>
    }

    return (
        <UserContext.Provider value={{ user, setUser, isAdmin: user?.role === 'admin' }}>
            <Routes>
                <Route path="/login" element={
                    isAuthenticated ? <Navigate to="/" /> : <Login onLoginSuccess={handleLoginSuccess} />
                } />
                <Route path="/" element={
                    isAuthenticated ? <Layout><Dashboard /></Layout> : <Navigate to="/login" />
                } />
                <Route path="/contracts" element={
                    isAuthenticated ? <Layout><Contracts /></Layout> : <Navigate to="/login" />
                } />
                <Route path="/invoices" element={
                    isAuthenticated ? <Layout><Invoices /></Layout> : <Navigate to="/login" />
                } />
                <Route path="/lists" element={
                    isAuthenticated ? <Layout><Lists /></Layout> : <Navigate to="/login" />
                } />
                <Route path="/calendar" element={
                    isAuthenticated ? <Layout><Calendar /></Layout> : <Navigate to="/login" />
                } />
                <Route path="/protected" element={
                    isAuthenticated ? <Layout><ProtectedContracts /></Layout> : <Navigate to="/login" />
                } />
                <Route path="/admin" element={
                    isAuthenticated && user?.role === 'admin'
                        ? <Layout><AdminPanel /></Layout>
                        : <Navigate to="/" />
                } />
            </Routes>
        </UserContext.Provider>
    )
}

function App() {
    return (
        <Router>
            <AppRoutes />
        </Router>
    )
}

export default App

