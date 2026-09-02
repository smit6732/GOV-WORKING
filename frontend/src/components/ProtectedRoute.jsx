import React from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

export function RequireAuth({ children }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  return children
}

export function RequireRole({ roles, children }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (!roles.includes(user.role)) {
    return (
      <div className="bg-white rounded-lg shadow p-8 text-center text-slate-500">
        You do not have permission to view this page.
      </div>
    )
  }
  return children
}
