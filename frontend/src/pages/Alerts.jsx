import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api.js'
import { Card, ErrorBanner, Spinner } from '../components/ui.jsx'
import useAlertsSocket from '../hooks/useAlertsSocket.js'

export default function Alerts() {
  const { alerts: liveAlerts, connected } = useAlertsSocket()
  const [history, setHistory] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.get('/alerts').then((res) => setHistory(res.data.items)).catch((e) => setError(e.response?.data?.detail || 'Failed to load alerts'))
  }, [])

  return (
    <div className="space-y-3">
      <ErrorBanner message={error} />

      <Card>
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-slate-700">Live alerts</h3>
          <span className={`text-xs flex items-center gap-1.5 ${connected ? 'text-green-600' : 'text-slate-400'}`}>
            <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-slate-300'}`} />
            {connected ? 'Connected' : 'Reconnecting…'}
          </span>
        </div>
        {liveAlerts.length === 0 ? (
          <div className="text-sm text-slate-400">
            No alerts yet this session. Tag a plate on the Tags page — when it's seen on an ANPR-tracked
            feed, it appears here in real time.
          </div>
        ) : (
          <div className="space-y-2">
            {liveAlerts.map((a, i) => (
              <AlertRow key={i} a={a} />
            ))}
          </div>
        )}
      </Card>

      <Card className="overflow-x-auto">
        <h3 className="font-semibold text-slate-700 mb-3">Alert history</h3>
        {!history ? (
          <Spinner />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 uppercase border-b">
                <th className="py-2 pr-3">Plate</th>
                <th className="py-2 pr-3">Camera</th>
                <th className="py-2 pr-3">District</th>
                <th className="py-2 pr-3">Department</th>
                <th className="py-2 pr-3">Reason</th>
                <th className="py-2 pr-3">Time</th>
                <th className="py-2 pr-3"></th>
              </tr>
            </thead>
            <tbody>
              {history.map((a) => (
                <tr key={a.id} className="border-b last:border-0">
                  <td className="py-2 pr-3 font-semibold">{a.plate_no}</td>
                  <td className="py-2 pr-3">{a.camera_id}</td>
                  <td className="py-2 pr-3">{a.district}</td>
                  <td className="py-2 pr-3">{a.department}</td>
                  <td className="py-2 pr-3">{a.matched_reason || '—'}</td>
                  <td className="py-2 pr-3">{new Date(a.created_at).toLocaleString()}</td>
                  <td className="py-2 pr-3">
                    <Link to={`/vehicle-search?plate=${encodeURIComponent(a.plate_no)}`} className="text-gujgov-700 underline text-xs">
                      View route
                    </Link>
                  </td>
                </tr>
              ))}
              {history.length === 0 && (
                <tr><td colSpan={7} className="py-4 text-center text-slate-400">No alerts triggered yet.</td></tr>
              )}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}

function AlertRow({ a }) {
  return (
    <div className="border border-amber-200 bg-amber-50 rounded p-2 text-sm flex items-center justify-between">
      <div>
        <span className="font-semibold">{a.plate_no}</span> seen on <span className="font-medium">{a.camera_id}</span>
        {a.district && <span className="text-slate-500"> · {a.district}</span>}
        {a.matched_reason && <span className="text-slate-500"> · {a.matched_reason}</span>}
      </div>
      <span className="text-xs text-slate-500">{new Date(a.timestamp).toLocaleTimeString()}</span>
    </div>
  )
}
