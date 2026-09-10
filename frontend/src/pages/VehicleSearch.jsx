import React, { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CircleMarker, Popup, Polyline } from 'react-leaflet'
import api from '../api.js'
import { Card, ErrorBanner, Spinner } from '../components/ui.jsx'
import MapBase from '../components/MapBase.jsx'

export default function VehicleSearch() {
  const [searchParams] = useSearchParams()
  const initialPlate = searchParams.get('plate') || ''
  const [filters, setFilters] = useState({ plate: initialPlate, camera_id: '', start_time: '', end_time: '' })
  const [results, setResults] = useState(null)
  const [history, setHistory] = useState(null)
  const [activePlate, setActivePlate] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const update = (key) => (e) => setFilters((f) => ({ ...f, [key]: e.target.value }))

  useEffect(() => {
    if (initialPlate) {
      search()
      showHistory(initialPlate)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function search(e) {
    e?.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v))
      const res = await api.get('/vehicles/search', { params })
      setResults(res.data.items)
    } catch (err) {
      setError(err.response?.data?.detail || 'Search failed')
    } finally {
      setLoading(false)
    }
  }

  async function showHistory(plate) {
    setError(null)
    setActivePlate(plate)
    try {
      const res = await api.get(`/vehicles/${encodeURIComponent(plate)}/history`)
      setHistory(res.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not load movement history')
      setHistory(null)
    }
  }

  const points = (history?.points || []).filter((h) => h.latitude != null && h.longitude != null)
  const segments = history?.segments || []

  return (
    <div className="space-y-3">
      <ErrorBanner message={error} />

      <Card>
        <form onSubmit={search} className="flex flex-wrap gap-3 items-end">
          <Field label="Plate No.">
            <input
              value={filters.plate}
              onChange={update('plate')}
              placeholder="e.g. GJ01AB1234"
              className="border border-slate-300 rounded px-2 py-1.5 text-sm w-40"
            />
          </Field>
          <Field label="Camera ID">
            <input
              value={filters.camera_id}
              onChange={update('camera_id')}
              placeholder="CAM-M2-001"
              className="border border-slate-300 rounded px-2 py-1.5 text-sm w-40"
            />
          </Field>
          <Field label="From">
            <input type="datetime-local" value={filters.start_time} onChange={update('start_time')}
              className="border border-slate-300 rounded px-2 py-1.5 text-sm" />
          </Field>
          <Field label="To">
            <input type="datetime-local" value={filters.end_time} onChange={update('end_time')}
              className="border border-slate-300 rounded px-2 py-1.5 text-sm" />
          </Field>
          <button type="submit" className="px-4 py-1.5 bg-gujgov-700 text-white rounded text-sm font-medium">
            Search
          </button>
        </form>
      </Card>

      {loading && <Spinner />}

      {results && (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 uppercase border-b">
                <th className="py-2 pr-3">Plate</th>
                <th className="py-2 pr-3">Camera</th>
                <th className="py-2 pr-3">District</th>
                <th className="py-2 pr-3">Department</th>
                <th className="py-2 pr-3">Time</th>
                <th className="py-2 pr-3">Confidence</th>
                <th className="py-2 pr-3"></th>
              </tr>
            </thead>
            <tbody>
              {results.map((r, i) => (
                <tr key={i} className="border-b last:border-0">
                  <td className="py-2 pr-3 font-semibold">{r.plate_no || '—'}</td>
                  <td className="py-2 pr-3">{r.camera_id}</td>
                  <td className="py-2 pr-3">{r.district}</td>
                  <td className="py-2 pr-3">{r.department}</td>
                  <td className="py-2 pr-3">{r.timestamp ? new Date(r.timestamp).toLocaleString() : '—'}</td>
                  <td className="py-2 pr-3">{r.plate_confidence != null ? `${(r.plate_confidence * 100).toFixed(0)}%` : '—'}</td>
                  <td className="py-2 pr-3">
                    {r.plate_no && (
                      <button
                        onClick={() => showHistory(r.plate_no)}
                        className="text-gujgov-700 underline text-xs"
                      >
                        Show route
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {results.length === 0 && (
                <tr><td colSpan={7} className="py-4 text-center text-slate-400">No detections match this search.</td></tr>
              )}
            </tbody>
          </table>
        </Card>
      )}

      {activePlate && (
        <Card className="p-0 overflow-hidden" style={{ height: '60vh' }}>
          <div className="p-2 border-b flex flex-wrap items-center justify-between gap-2 bg-slate-50">
            <div className="text-sm font-semibold">
              Movement history — {activePlate} ({points.length} located detection{points.length === 1 ? '' : 's'})
            </div>
            {segments.length > 0 && (
              <span
                className="text-xs bg-amber-50 text-amber-800 border border-amber-200 px-2 py-0.5 rounded font-medium cursor-help"
                title="Calculated using a public road-routing service; the actual path the vehicle took between camera checkpoints may vary."
              >
                📍 Suggested probable route between detections
              </span>
            )}
          </div>
          <div style={{ height: 'calc(100% - 42px)' }}>
            <MapBase height="100%">
              {segments.map((seg, i) => (
                <Polyline
                  key={i}
                  positions={seg.coordinates}
                  pathOptions={
                    seg.route_type === 'road_path'
                      ? { color: '#2563eb', weight: 4, opacity: 0.85 }
                      : { color: '#64748b', weight: 3, dashArray: '6, 8', opacity: 0.7 }
                  }
                />
              ))}
              {segments.length === 0 && points.length > 1 && (
                <Polyline
                  positions={points.map((p) => [p.latitude, p.longitude])}
                  pathOptions={{ color: '#2563eb', weight: 3, opacity: 0.85 }}
                />
              )}
              {points.map((p, i) => (
                <CircleMarker
                  key={p.event_id}
                  center={[p.latitude, p.longitude]}
                  radius={7}
                  pathOptions={{ color: '#2563eb', fillColor: '#2563eb', fillOpacity: 0.85 }}
                >
                  <Popup>
                    <div className="text-sm space-y-1">
                      <div className="font-semibold">#{i + 1} · {p.camera_id}</div>
                      <div>{p.district} · {p.department}</div>
                      <div>{new Date(p.timestamp).toLocaleString()}</div>
                    </div>
                  </Popup>
                </CircleMarker>
              ))}
            </MapBase>
          </div>
        </Card>
      )}
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-500 mb-1">{label}</label>
      {children}
    </div>
  )
}
