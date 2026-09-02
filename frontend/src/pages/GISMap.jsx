import React, { useEffect, useState, useMemo } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup, LayersControl } from 'react-leaflet'
import api from '../api.js'
import { Card, StatusBadge, SyntheticBadge, ErrorBanner } from '../components/ui.jsx'

const GUJARAT_CENTER = [22.6, 71.6]

const STATUS_COLORS = {
  Active: '#16a34a',
  Offline: '#dc2626',
  Maintenance: '#d97706',
}

export default function GISMap() {
  const [options, setOptions] = useState(null)
  const [geojson, setGeojson] = useState(null)
  const [error, setError] = useState(null)
  const [filters, setFilters] = useState({
    department: '',
    camera_type: '',
    district: '',
    connectivity_status: '',
  })

  useEffect(() => {
    api.get('/cameras/meta/options').then((res) => setOptions(res.data)).catch(() => {})
  }, [])

  useEffect(() => {
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v))
    api
      .get('/cameras/geojson', { params })
      .then((res) => setGeojson(res.data))
      .catch((e) => setError(e.response?.data?.detail || 'Failed to load map data'))
  }, [filters])

  const features = geojson?.features || []

  const update = (key) => (e) => setFilters((f) => ({ ...f, [key]: e.target.value }))

  return (
    <div className="space-y-3">
      <ErrorBanner message={error} />
      <Card className="flex flex-wrap gap-3 items-end">
        <FilterSelect label="Department" value={filters.department} onChange={update('department')} options={options?.departments} />
        <FilterSelect label="Camera Type" value={filters.camera_type} onChange={update('camera_type')} options={options?.camera_types} />
        <FilterSelect label="District" value={filters.district} onChange={update('district')} options={options?.districts} />
        <FilterSelect label="Status" value={filters.connectivity_status} onChange={update('connectivity_status')} options={options?.connectivity_statuses} />
        <span className="text-sm text-slate-500 ml-auto">{features.length} cameras shown</span>
      </Card>

      <Card className="p-0 overflow-hidden" style={{ height: '70vh' }}>
        <MapContainer center={GUJARAT_CENTER} zoom={7} style={{ height: '100%' }}>
          <LayersControl position="topright">
            <LayersControl.BaseLayer checked name="Streets">
              <TileLayer
                attribution='&copy; OpenStreetMap contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
            </LayersControl.BaseLayer>
            <LayersControl.BaseLayer name="Satellite">
              <TileLayer
                attribution="Tiles &copy; Esri"
                url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
              />
            </LayersControl.BaseLayer>
          </LayersControl>
          {features.map((f) => (
            <CircleMarker
              key={f.properties.id}
              center={[f.geometry.coordinates[1], f.geometry.coordinates[0]]}
              radius={5}
              pathOptions={{
                color: STATUS_COLORS[f.properties.connectivity_status] || '#64748b',
                fillColor: STATUS_COLORS[f.properties.connectivity_status] || '#64748b',
                fillOpacity: 0.75,
                weight: 1,
              }}
            >
              <Popup>
                <div className="text-sm space-y-1">
                  <div className="font-semibold">{f.properties.camera_id}</div>
                  <div>{f.properties.district} · {f.properties.nearest_station}</div>
                  <div>{f.properties.camera_type} · {f.properties.vendor}</div>
                  <div>{f.properties.department}</div>
                  <div className="flex gap-1 mt-1">
                    <StatusBadge status={f.properties.connectivity_status} />
                    <SyntheticBadge isSynthetic={f.properties.is_synthetic} />
                  </div>
                  {f.properties.is_ageing && (
                    <div className="text-purple-600 text-xs font-medium">
                      ⚠ Ageing ({f.properties.age_years} yrs in service)
                    </div>
                  )}
                </div>
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>
      </Card>

      <div className="flex gap-4 text-xs text-slate-500">
        <Legend color={STATUS_COLORS.Active} label="Active" />
        <Legend color={STATUS_COLORS.Offline} label="Offline" />
        <Legend color={STATUS_COLORS.Maintenance} label="Maintenance" />
      </div>
    </div>
  )
}

function Legend({ color, label }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="inline-block w-3 h-3 rounded-full" style={{ background: color }} />
      {label}
    </span>
  )
}

function FilterSelect({ label, value, onChange, options }) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-500 mb-1">{label}</label>
      <select
        value={value}
        onChange={onChange}
        className="border border-slate-300 rounded px-2 py-1.5 text-sm min-w-[160px]"
      >
        <option value="">All</option>
        {(options || []).map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </div>
  )
}
