import React, { useEffect, useState, useCallback } from 'react'
import api from '../api.js'
import { Card, ErrorBanner, Spinner } from '../components/ui.jsx'

const PAGE_SIZE = 30
const ACTIONS = ['', 'create', 'update', 'delete', 'bulk_upload', 'login']

export default function AuditLogs() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [action, setAction] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    const params = { page, page_size: PAGE_SIZE }
    if (action) params.action = action
    api
      .get('/audit-logs', { params })
      .then((res) => setData(res.data))
      .catch((e) => setError(e.response?.data?.detail || 'Failed to load audit logs'))
      .finally(() => setLoading(false))
  }, [page, action])

  useEffect(() => { load() }, [load])

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <div className="space-y-3">
      <ErrorBanner message={error} />
      <Card className="flex items-end gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">Action</label>
          <select
            value={action}
            onChange={(e) => { setPage(1); setAction(e.target.value) }}
            className="border border-slate-300 rounded px-2 py-1.5 text-sm"
          >
            {ACTIONS.map((a) => <option key={a} value={a}>{a || 'All'}</option>)}
          </select>
        </div>
      </Card>

      <Card className="p-0 overflow-x-auto">
        {loading ? (
          <Spinner />
        ) : (
          <table className="min-w-full text-sm">
            <thead className="bg-slate-100 text-slate-600 text-xs uppercase">
              <tr>
                <th className="px-3 py-2 text-left">Timestamp (UTC)</th>
                <th className="px-3 py-2 text-left">User</th>
                <th className="px-3 py-2 text-left">Action</th>
                <th className="px-3 py-2 text-left">Entity</th>
                <th className="px-3 py-2 text-left">Entity ID</th>
                <th className="px-3 py-2 text-left">Details</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((log) => (
                <tr key={log.id} className="border-t border-slate-100">
                  <td className="px-3 py-2 whitespace-nowrap">{new Date(log.timestamp + 'Z').toLocaleString()}</td>
                  <td className="px-3 py-2">{log.user_email}</td>
                  <td className="px-3 py-2">
                    <span className="px-2 py-0.5 rounded-full text-xs bg-slate-100">{log.action}</span>
                  </td>
                  <td className="px-3 py-2">{log.entity_type}</td>
                  <td className="px-3 py-2">{log.entity_id}</td>
                  <td className="px-3 py-2 max-w-md truncate text-xs text-slate-500" title={log.details}>{log.details}</td>
                </tr>
              ))}
              {data?.items.length === 0 && (
                <tr><td colSpan={6} className="px-3 py-8 text-center text-slate-400">No audit log entries</td></tr>
              )}
            </tbody>
          </table>
        )}
      </Card>

      {data && (
        <div className="flex items-center justify-between text-sm text-slate-500">
          <span>{data.total} entries total</span>
          <div className="flex gap-2 items-center">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="px-2 py-1 border rounded disabled:opacity-40">Prev</button>
            <span>Page {page} / {totalPages}</span>
            <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="px-2 py-1 border rounded disabled:opacity-40">Next</button>
          </div>
        </div>
      )}
    </div>
  )
}
