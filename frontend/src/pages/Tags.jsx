import React, { useEffect, useState } from 'react'
import api from '../api.js'
import { useAuth } from '../context/AuthContext.jsx'
import { Card, ErrorBanner, Spinner } from '../components/ui.jsx'

export default function Tags() {
  const { user } = useAuth()
  const [tags, setTags] = useState(null)
  const [error, setError] = useState(null)
  const [plate, setPlate] = useState('')
  const [reason, setReason] = useState('')
  const [global, setGlobal] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  function load() {
    api.get('/tags').then((res) => setTags(res.data)).catch((e) => setError(e.response?.data?.detail || 'Failed to load tags'))
  }

  useEffect(load, [])

  async function submit(e) {
    e.preventDefault()
    if (!plate.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      await api.post('/tags', {
        plate_no: plate.trim(),
        reason: reason.trim() || null,
        department: global ? null : user?.department || null,
      })
      setPlate('')
      setReason('')
      load()
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not tag plate')
    } finally {
      setSubmitting(false)
    }
  }

  async function remove(id) {
    try {
      await api.delete(`/tags/${id}`)
      load()
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not remove tag')
    }
  }

  return (
    <div className="space-y-3">
      <ErrorBanner message={error} />

      <Card>
        <h3 className="font-semibold text-slate-700 mb-3">Tag a plate for alerting</h3>
        <form onSubmit={submit} className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">Plate No.</label>
            <input
              autoFocus
              value={plate}
              onChange={(e) => setPlate(e.target.value)}
              placeholder="e.g. GJ01AB1234"
              className="border border-slate-300 rounded px-2 py-1.5 text-sm w-44"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">Reason</label>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. stolen vehicle report #..."
              className="border border-slate-300 rounded px-2 py-1.5 text-sm w-64"
            />
          </div>
          {user?.role === 'super_admin' && (
            <label className="flex items-center gap-1.5 text-sm text-slate-600 pb-1.5">
              <input type="checkbox" checked={global} onChange={(e) => setGlobal(e.target.checked)} />
              Global (all departments)
            </label>
          )}
          <button
            type="submit"
            disabled={submitting || !plate.trim()}
            className="px-4 py-1.5 bg-gujgov-700 text-white rounded text-sm font-medium disabled:opacity-40"
          >
            Tag plate
          </button>
        </form>
      </Card>

      <Card className="overflow-x-auto">
        <h3 className="font-semibold text-slate-700 mb-3">Active tags</h3>
        {!tags ? (
          <Spinner />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 uppercase border-b">
                <th className="py-2 pr-3">Plate</th>
                <th className="py-2 pr-3">Reason</th>
                <th className="py-2 pr-3">Scope</th>
                <th className="py-2 pr-3">Tagged by</th>
                <th className="py-2 pr-3">Since</th>
                <th className="py-2 pr-3"></th>
              </tr>
            </thead>
            <tbody>
              {tags.map((t) => (
                <tr key={t.id} className="border-b last:border-0">
                  <td className="py-2 pr-3 font-semibold">{t.plate_no}</td>
                  <td className="py-2 pr-3">{t.reason || '—'}</td>
                  <td className="py-2 pr-3">{t.department || 'All departments'}</td>
                  <td className="py-2 pr-3">{t.tagged_by || '—'}</td>
                  <td className="py-2 pr-3">{new Date(t.created_at).toLocaleString()}</td>
                  <td className="py-2 pr-3">
                    <button onClick={() => remove(t.id)} className="text-red-600 underline text-xs">Remove</button>
                  </td>
                </tr>
              ))}
              {tags.length === 0 && (
                <tr><td colSpan={6} className="py-4 text-center text-slate-400">No plates tagged yet.</td></tr>
              )}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}
