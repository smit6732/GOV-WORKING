import React, { useEffect, useState, useRef } from 'react'
import { MapContainer, TileLayer, GeoJSON } from 'react-leaflet'
import api from '../api.js'
import { Card, ErrorBanner, Spinner } from '../components/ui.jsx'

const GUJARAT_CENTER = [22.6, 71.6]

export default function Coverage() {
  const [radius, setRadius] = useState(300)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  // react-leaflet's <GeoJSON> only redraws on remount, not on data-prop changes,
  // so bump a version counter on every successful fetch and fold it into the
  // layer `key` below — otherwise clicking "Recompute" at the same radius would
  // silently leave the previous polygons on screen.
  const versionRef = useRef(0)
  const [version, setVersion] = useState(0)

  const load = (r) => {
    setLoading(true)
    api
      .get('/coverage/gap-analysis', { params: { radius_m: r } })
      .then((res) => {
        setData(res.data)
        versionRef.current += 1
        setVersion(versionRef.current)
      })
      .catch((e) => setError(e.response?.data?.detail || 'Failed to compute coverage'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load(radius) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const exportCsv = () => {
    const token = localStorage.getItem('token')
    fetch(`/api/coverage/gap-analysis/export?radius_m=${radius}`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'coverage_gap_analysis.csv'
        a.click()
        URL.revokeObjectURL(url)
      })
  }

  return (
    <div className="space-y-4">
      <ErrorBanner message={error} />
      <Card className="flex flex-wrap items-end gap-4">
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">
            Per-camera coverage radius: {radius} m
          </label>
          <input
            type="range"
            min={50}
            max={1500}
            step={50}
            value={radius}
            onChange={(e) => setRadius(Number(e.target.value))}
            onMouseUp={() => load(radius)}
            onTouchEnd={() => load(radius)}
            className="w-64"
          />
        </div>
        <button onClick={() => load(radius)} className="px-3 py-1.5 text-sm rounded bg-gujgov-600 hover:bg-gujgov-700 text-white">
          Recompute
        </button>
        <button onClick={exportCsv} className="px-3 py-1.5 text-sm rounded bg-gujgov-700 hover:bg-gujgov-800 text-white ml-auto">
          Export Gap Report CSV
        </button>
      </Card>

      {data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <SummaryStat label="State Region" value={`${data.summary.total_region_km2} km²`} />
          <SummaryStat label="Covered" value={`${data.summary.total_covered_km2} km²`} accent="text-green-600" />
          <SummaryStat label="Uncovered Gap" value={`${data.summary.total_gap_km2} km²`} accent="text-red-600" />
          <SummaryStat label="Coverage %" value={`${data.summary.coverage_pct}%`} accent="text-gujgov-700" />
        </div>
      )}

      <Card className="p-0 overflow-hidden" style={{ height: '65vh' }}>
        {loading ? (
          <Spinner />
        ) : (
          <MapContainer center={GUJARAT_CENTER} zoom={7} style={{ height: '100%' }}>
            <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
            {data?.gap_geojson && (
              <GeoJSON
                key={`gap-${version}`}
                data={data.gap_geojson}
                style={{ color: '#dc2626', weight: 1, fillColor: '#dc2626', fillOpacity: 0.35 }}
                onEachFeature={(f, layer) => layer.bindPopup(`${f.properties.district}: ${f.properties.gap_area_km2} km² uncovered`)}
              />
            )}
            {data?.covered_geojson && (
              <GeoJSON
                key={`covered-${version}`}
                data={data.covered_geojson}
                style={{ color: '#16a34a', weight: 1, fillColor: '#16a34a', fillOpacity: 0.25 }}
                onEachFeature={(f, layer) => layer.bindPopup(`${f.properties.district}: ${f.properties.covered_area_km2} km² covered`)}
              />
            )}
          </MapContainer>
        )}
      </Card>
      <div className="flex gap-4 text-xs text-slate-500">
        <Legend color="#16a34a" label="Covered (buffered camera union)" />
        <Legend color="#dc2626" label="Coverage gap" />
      </div>

      {data && (
        <Card className="overflow-x-auto">
          <h3 className="font-semibold text-sm text-slate-700 mb-2">Per-district coverage</h3>
          <table className="min-w-full text-sm">
            <thead className="bg-slate-100 text-slate-600 text-xs uppercase">
              <tr>
                <th className="px-3 py-2 text-left">District</th>
                <th className="px-3 py-2 text-right">Cameras</th>
                <th className="px-3 py-2 text-right">Region km²</th>
                <th className="px-3 py-2 text-right">Covered km²</th>
                <th className="px-3 py-2 text-right">Gap km²</th>
                <th className="px-3 py-2 text-right">Coverage %</th>
              </tr>
            </thead>
            <tbody>
              {data.districts
                .slice()
                .sort((a, b) => a.coverage_pct - b.coverage_pct)
                .map((d) => (
                  <tr key={d.district} className="border-t border-slate-100">
                    <td className="px-3 py-2">{d.district}</td>
                    <td className="px-3 py-2 text-right">{d.camera_count}</td>
                    <td className="px-3 py-2 text-right">{d.region_area_km2}</td>
                    <td className="px-3 py-2 text-right">{d.covered_area_km2}</td>
                    <td className="px-3 py-2 text-right">{d.gap_area_km2}</td>
                    <td className="px-3 py-2 text-right">
                      <span className={d.coverage_pct < 20 ? 'text-red-600 font-semibold' : d.coverage_pct < 50 ? 'text-amber-600' : 'text-green-600'}>
                        {d.coverage_pct}%
                      </span>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}

function SummaryStat({ label, value, accent = 'text-slate-800' }) {
  return (
    <Card className="text-center">
      <div className={`text-2xl font-bold ${accent}`}>{value}</div>
      <div className="text-xs text-slate-500">{label}</div>
    </Card>
  )
}

function Legend({ color, label }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="inline-block w-3 h-3 rounded" style={{ background: color, opacity: 0.6 }} />
      {label}
    </span>
  )
}
