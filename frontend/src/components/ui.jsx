import React from 'react'

export function Card({ children, className = '', style }) {
  return <div className={`bg-white rounded-lg shadow p-4 ${className}`} style={style}>{children}</div>
}

export function StatCard({ label, value, accent = 'text-slate-800', sub }) {
  return (
    <Card className="flex flex-col gap-1">
      <span className="text-xs uppercase tracking-wide text-slate-500">{label}</span>
      <span className={`text-3xl font-bold ${accent}`}>{value}</span>
      {sub && <span className="text-xs text-slate-400">{sub}</span>}
    </Card>
  )
}

const STATUS_STYLES = {
  Active: 'bg-green-100 text-green-700',
  Offline: 'bg-red-100 text-red-700',
  Maintenance: 'bg-amber-100 text-amber-700',
}

export function StatusBadge({ status }) {
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLES[status] || 'bg-slate-100 text-slate-600'}`}>
      {status}
    </span>
  )
}

export function SyntheticBadge({ isSynthetic }) {
  if (!isSynthetic) {
    return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">Live-registered</span>
  }
  return (
    <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-700" title="Synthetic demo data — not a real device">
      Demo / Synthetic
    </span>
  )
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center p-8 text-slate-400 text-sm">
      Loading…
    </div>
  )
}

export function ErrorBanner({ message }) {
  if (!message) return null
  return (
    <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded p-3 mb-3">
      {message}
    </div>
  )
}
