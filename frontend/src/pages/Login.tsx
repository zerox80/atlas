import React, { useState } from 'react'
import { motion } from 'framer-motion'
import api from '../api'

interface LoginProps {
    onLoginSuccess: () => void
}

const Login: React.FC<LoginProps> = ({ onLoginSuccess }) => {
    const [username, setUsername] = useState('')
    const [password, setPassword] = useState('')
    const [otp, setOtp] = useState('')
    const [error, setError] = useState('')
    const [isLoading, setIsLoading] = useState(false)
    const [isTwoFactorInfo, setIsTwoFactorInfo] = useState(false)

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setError('')
        setIsLoading(true)

        // Create form data for OAuth2
        const formData = new FormData()
        formData.append('username', username)
        formData.append('password', password)
        if (otp) {
            formData.append('client_secret', otp)
        }

        try {
            await api.post('/token', formData, { withCredentials: true })
            // Token is now set as HttpOnly cookie by backend - no localStorage needed
            onLoginSuccess()
        } catch (err: any) {
            if (err.response?.status === 401 && err.response?.data?.detail === "2FA Required") {
                setIsTwoFactorInfo(true)
                setError("Two-Factor Authentication Required")
            } else if (err.response?.status === 401 && err.response?.data?.detail === "Invalid 2FA Code") {
                setError("Invalid Code. Please try again.")
            } else {
                setError('Invalid credentials')
            }
        } finally {
            setIsLoading(false)
        }
    }

    return (
        <div className="min-h-screen flex items-center justify-center bg-gray-950 relative overflow-hidden">
            {/* Background Decorative Elements */}
            <div className="absolute top-0 left-0 w-96 h-96 bg-blue-600/20 rounded-full blur-3xl -translate-x-1/2 -translate-y-1/2"></div>
            <div className="absolute bottom-0 right-0 w-96 h-96 bg-purple-600/20 rounded-full blur-3xl translate-x-1/2 translate-y-1/2"></div>

            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
                className="w-full max-w-md p-8 rounded-2xl bg-gray-900/60 backdrop-blur-xl border border-gray-800 shadow-2xl relative z-10"
            >
                <h2 className="text-3xl font-bold mb-6 text-center text-white">
                    {isTwoFactorInfo ? 'Two-Factor Authentication' : 'Welcome Back'}
                </h2>
                {error && <div className="bg-red-500/10 border border-red-500/50 text-red-500 p-3 rounded mb-4 text-center">{error}</div>}

                <form onSubmit={handleSubmit} className="space-y-6">
                    {!isTwoFactorInfo ? (
                        <>
                            <div>
                                <label className="block text-sm font-medium text-gray-400 mb-2">Username</label>
                                <input
                                    type="text"
                                    value={username}
                                    onChange={(e) => setUsername(e.target.value)}
                                    className="w-full px-4 py-3 rounded-lg bg-gray-800 border border-gray-700 text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
                                    placeholder="Enter your username"
                                    required
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-400 mb-2">Password</label>
                                <input
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    className="w-full px-4 py-3 rounded-lg bg-gray-800 border border-gray-700 text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
                                    placeholder="••••••••"
                                    required
                                />
                            </div>
                        </>
                    ) : (
                        <div>
                            <label className="block text-sm font-medium text-gray-400 mb-2">Authenticator Code</label>
                            <input
                                type="text"
                                value={otp}
                                onChange={(e) => setOtp(e.target.value)}
                                className="w-full px-4 py-3 rounded-lg bg-gray-800 border border-gray-700 text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors text-center tracking-widest text-2xl"
                                placeholder="000 000"
                                maxLength={6}
                                autoFocus
                                required
                            />
                        </div>
                    )}

                    <button
                        type="submit"
                        disabled={isLoading}
                        className="w-full py-3 px-4 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white font-medium rounded-lg transition-all transform hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-blue-500/30"
                    >
                        {isLoading ? 'Verifying...' : (isTwoFactorInfo ? 'Verify Code' : 'Sign In')}
                    </button>
                    {isTwoFactorInfo && (
                        <button
                            type="button"
                            onClick={() => { setIsTwoFactorInfo(false); setError(''); }}
                            className="w-full text-sm text-gray-400 hover:text-white transition-colors"
                        >
                            Back to Login
                        </button>
                    )}
                </form>
            </motion.div>
        </div>
    )
}

export default Login
