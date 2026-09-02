import React, { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { ErrorBanner } from '../components/ui.jsx'

const DEMO_ACCOUNTS = [
  { role: 'Super Admin', email: 'superadmin@gujaratpolice.gov.in', password: 'SuperAdmin@123' },
  { role: 'Department Admin', email: 'deptadmin@gujaratpolice.gov.in', password: 'DeptAdmin@123' },
  { role: 'Viewer', email: 'viewer@gujaratpolice.gov.in', password: 'Viewer@123' },
]

export default function Login() {
  const { user, login, loading, error } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()

  if (user) return <Navigate to="/" replace />

  const handleSubmit = async (e) => {
    e.preventDefault()
    const ok = await login(email, password)
    if (ok) navigate('/')
  }

  const fillDemo = (acc) => {
    setEmail(acc.email)
    setPassword(acc.password)
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gujgov-900 px-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-8">
        <h1 className="text-xl font-bold text-gujgov-900 text-center">
          Gujarat CCTV GIS Registry
        </h1>
        <p className="text-center text-slate-500 text-sm mt-1 mb-6">
          Centralised CCTV Registry &amp; GIS Mapping — sign in to continue
        </p>

        <ErrorBanner message={error} />

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gujgov-600"
              placeholder="you@gujaratpolice.gov.in"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gujgov-600"
              placeholder="••••••••"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-gujgov-600 hover:bg-gujgov-700 text-white font-medium py-2 rounded disabled:opacity-50"
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <div className="mt-6 border-t pt-4">
          <p className="text-xs text-slate-400 mb-2">Demo accounts (click to autofill):</p>
          <div className="grid grid-cols-1 gap-2">
            {DEMO_ACCOUNTS.map((acc) => (
              <button
                key={acc.email}
                onClick={() => fillDemo(acc)}
                type="button"
                className="text-left text-xs bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded px-3 py-2"
              >
                <span className="font-semibold">{acc.role}</span> — {acc.email}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
