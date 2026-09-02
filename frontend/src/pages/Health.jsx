import React, { useEffect, useState } from 'react'
import api from '../api.js'
import { Card, StatCard, StatusBadge, ErrorBanner, Spinner } from '../components/ui.jsx'

export default function Health() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [flagFilter, setFlagFilter] = useState('')

  useEffect(() => {
    api.get('/health/ageing').then((res) => setData(res.data)).catch((e) => setError(e.response?.data?.detail || 'Failed to load health report'))
  }, [])

  if (error) return <ErrorBanner message={error} />
  if (!data) return <Spinner />

  const items = flagFilter ? data.items.filter((i) => i.flags.includes(flagFilter)) : data.items

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Needs Attention" value={data.needs_attention_count} accent="text-red-600" />
        <StatCard label="Ageing" value={data.ageing_count} accent="text-purple-600" sub={`>= ${data.expected_service_life_years} yrs in service`} />
        <StatCard label="Offline" value={data.offline_count} accent="text-red-600" />
        <StatCard label="Maintenance" value={data.maintenance_count} accent="text-amber-600" />
      </div>

      <Card className="p-0 overflow-x-auto">
        <div className="flex items-center gap-2 p-3 border-b">
          <span className="text-sm font-medium text-slate-600">Filter:</span>
          {['', 'ageing', 'offline', 'maintenance'].map((f) => (
            <button
              key={f}
              onClick={() => setFlagFilter(f)}
              className={`px-3 py-1 rounded-full text-xs font-medium ${flagFilter === f ? 'bg-gujgov-600 text-white' : 'bg-slate-100 text-slate-600'}`}
            >
              {f || 'All flagged'}
            </button>
          ))}
        </div>
        <table className="min-w-full text-sm">
          <thead className="bg-slate-100 text-slate-600 text-xs uppercase">
            <tr>
              <th className="px-3 py-2 text-left">Camera ID</th>
              <th className="px-3 py-2 text-left">District</th>
              <th className="px-3 py-2 text-left">Department</th>
              <th className="px-3 py-2 text-left">Install Year</th>
              <th className="px-3 py-2 text-left">Age (yrs)</th>
              <th className="px-3 py-2 text-left">Status</th>
              <th className="px-3 py-2 text-left">Flags</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.id} className="border-t border-slate-100">
                <td className="px-3 py-2 font-medium">{c.camera_id}</td>
                <td className="px-3 py-2">{c.district}</td>
                <td className="px-3 py-2">{c.department}</td>
                <td className="px-3 py-2">{c.install_year}</td>
                <td className="px-3 py-2">{c.age_years}</td>
                <td className="px-3 py-2"><StatusBadge status={c.connectivity_status} /></td>
                <td className="px-3 py-2 space-x-1">
                  {c.flags.map((f) => (
                    <span key={f} className="px-2 py-0.5 rounded-full text-xs bg-red-100 text-red-700">{f}</span>
                  ))}
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={7} className="px-3 py-8 text-center text-slate-400">No flagged cameras for this filter</td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
