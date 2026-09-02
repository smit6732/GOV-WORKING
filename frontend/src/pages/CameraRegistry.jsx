import React, { useEffect, useState, useCallback } from 'react'
import api from '../api.js'
import { useAuth } from '../context/AuthContext.jsx'
import { Card, StatusBadge, SyntheticBadge, ErrorBanner, Spinner } from '../components/ui.jsx'

const PAGE_SIZE = 25

export default function CameraRegistry() {
  const { user } = useAuth()
  const canEdit = user.role === 'super_admin' || user.role === 'department_admin'

  const [options, setOptions] = useState(null)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({ department: '', camera_type: '', district: '', connectivity_status: '', search: '' })
  const [editing, setEditing] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    const params = { page, page_size: PAGE_SIZE, ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v)) }
    api
      .get('/cameras', { params })
      .then((res) => setData(res.data))
      .catch((e) => setError(e.response?.data?.detail || 'Failed to load cameras'))
      .finally(() => setLoading(false))
  }, [page, filters])

  useEffect(() => {
    api.get('/cameras/meta/options').then((res) => setOptions(res.data)).catch(() => {})
  }, [])

  useEffect(() => { load() }, [load])

  const updateFilter = (key) => (e) => {
    setPage(1)
    setFilters((f) => ({ ...f, [key]: e.target.value }))
  }

  const handleDelete = async (cam) => {
    if (!confirm(`Delete camera ${cam.camera_id}? This cannot be undone.`)) return
    try {
      await api.delete(`/cameras/${cam.id}`)
      load()
    } catch (e) {
      alert(e.response?.data?.detail || 'Delete failed')
    }
  }

  const exportCsv = () => {
    const params = new URLSearchParams(Object.fromEntries(Object.entries(filters).filter(([k, v]) => v && k !== 'search')))
    const token = localStorage.getItem('token')
    fetch(`/api/cameras/export?${params.toString()}`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'camera_registry_export.csv'
        a.click()
        URL.revokeObjectURL(url)
      })
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <div className="space-y-3">
      <ErrorBanner message={error} />
      <Card className="flex flex-wrap gap-3 items-end">
        <FilterSelect label="Department" value={filters.department} onChange={updateFilter('department')} options={options?.departments} />
        <FilterSelect label="Camera Type" value={filters.camera_type} onChange={updateFilter('camera_type')} options={options?.camera_types} />
        <FilterSelect label="District" value={filters.district} onChange={updateFilter('district')} options={options?.districts} />
        <FilterSelect label="Status" value={filters.connectivity_status} onChange={updateFilter('connectivity_status')} options={options?.connectivity_statuses} />
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">Search</label>
          <input
            value={filters.search}
            onChange={updateFilter('search')}
            placeholder="camera id / station"
            className="border border-slate-300 rounded px-2 py-1.5 text-sm"
          />
        </div>
        <button onClick={exportCsv} className="ml-auto bg-gujgov-700 hover:bg-gujgov-800 text-white text-sm px-3 py-1.5 rounded">
          Export CSV
        </button>
      </Card>

      <Card className="p-0 overflow-x-auto">
        {loading ? (
          <Spinner />
        ) : (
          <table className="min-w-full text-sm">
            <thead className="bg-slate-100 text-slate-600 text-xs uppercase">
              <tr>
                <th className="px-3 py-2 text-left">Camera ID</th>
                <th className="px-3 py-2 text-left">District</th>
                <th className="px-3 py-2 text-left">Department</th>
                <th className="px-3 py-2 text-left">Type</th>
                <th className="px-3 py-2 text-left">Vendor</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-left">Install Yr</th>
                <th className="px-3 py-2 text-left">Source</th>
                {canEdit && <th className="px-3 py-2 text-left">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {data?.items.map((c) => (
                <tr key={c.id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-3 py-2 font-medium">{c.camera_id}</td>
                  <td className="px-3 py-2">{c.district}</td>
                  <td className="px-3 py-2">{c.department}</td>
                  <td className="px-3 py-2">{c.camera_type}</td>
                  <td className="px-3 py-2">{c.vendor}</td>
                  <td className="px-3 py-2"><StatusBadge status={c.connectivity_status} /></td>
                  <td className="px-3 py-2">
                    {c.install_year} {c.is_ageing && <span className="text-purple-600" title="Ageing">⚠</span>}
                  </td>
                  <td className="px-3 py-2"><SyntheticBadge isSynthetic={c.is_synthetic} /></td>
                  {canEdit && (
                    <td className="px-3 py-2 space-x-2 whitespace-nowrap">
                      <button onClick={() => setEditing(c)} className="text-gujgov-600 hover:underline">Edit</button>
                      <button onClick={() => handleDelete(c)} className="text-red-600 hover:underline">Delete</button>
                    </td>
                  )}
                </tr>
              ))}
              {data?.items.length === 0 && (
                <tr><td colSpan={9} className="px-3 py-8 text-center text-slate-400">No cameras match these filters</td></tr>
              )}
            </tbody>
          </table>
        )}
      </Card>

      {data && (
        <div className="flex items-center justify-between text-sm text-slate-500">
          <span>{data.total} cameras total</span>
          <div className="flex gap-2 items-center">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="px-2 py-1 border rounded disabled:opacity-40">Prev</button>
            <span>Page {page} / {totalPages}</span>
            <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="px-2 py-1 border rounded disabled:opacity-40">Next</button>
          </div>
        </div>
      )}

      {editing && (
        <EditModal
          camera={editing}
          options={options}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load() }}
        />
      )}
    </div>
  )
}

function FilterSelect({ label, value, onChange, options }) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-500 mb-1">{label}</label>
      <select value={value} onChange={onChange} className="border border-slate-300 rounded px-2 py-1.5 text-sm min-w-[160px]">
        <option value="">All</option>
        {(options || []).map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  )
}

function EditModal({ camera, options, onClose, onSaved }) {
  const [form, setForm] = useState({
    district: camera.district,
    department: camera.department,
    nearest_station: camera.nearest_station || '',
    camera_type: camera.camera_type,
    vendor: camera.vendor || '',
    ownership: camera.ownership,
    latitude: camera.latitude,
    longitude: camera.longitude,
    storage_type: camera.storage_type || '',
    retention_days: camera.retention_days || '',
    install_year: camera.install_year || '',
    connectivity_status: camera.connectivity_status,
  })
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await api.put(`/cameras/${camera.id}`, {
        ...form,
        latitude: parseFloat(form.latitude),
        longitude: parseFloat(form.longitude),
        retention_days: form.retention_days ? parseInt(form.retention_days) : null,
        install_year: form.install_year ? parseInt(form.install_year) : null,
      })
      onSaved()
    } catch (e2) {
      setError(e2.response?.data?.detail || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full p-6 max-h-[90vh] overflow-y-auto">
        <h3 className="font-semibold text-lg mb-4">Edit {camera.camera_id}</h3>
        <ErrorBanner message={error} />
        <form onSubmit={submit} className="grid grid-cols-2 gap-3">
          <TextField label="District" value={form.district} onChange={set('district')} />
          <SelectField label="Department" value={form.department} onChange={set('department')} options={options?.departments} />
          <TextField label="Nearest Station" value={form.nearest_station} onChange={set('nearest_station')} />
          <SelectField label="Camera Type" value={form.camera_type} onChange={set('camera_type')} options={options?.camera_types} />
          <SelectField label="Vendor" value={form.vendor} onChange={set('vendor')} options={options?.vendors} />
          <SelectField label="Ownership" value={form.ownership} onChange={set('ownership')} options={options?.ownership_types} />
          <TextField label="Latitude" type="number" step="any" value={form.latitude} onChange={set('latitude')} />
          <TextField label="Longitude" type="number" step="any" value={form.longitude} onChange={set('longitude')} />
          <SelectField label="Storage Type" value={form.storage_type} onChange={set('storage_type')} options={options?.storage_types} />
          <TextField label="Retention (days)" type="number" value={form.retention_days} onChange={set('retention_days')} />
          <TextField label="Install Year" type="number" value={form.install_year} onChange={set('install_year')} />
          <SelectField label="Connectivity Status" value={form.connectivity_status} onChange={set('connectivity_status')} options={options?.connectivity_statuses} />

          <div className="col-span-2 flex justify-end gap-2 mt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm rounded border">Cancel</button>
            <button type="submit" disabled={saving} className="px-4 py-2 text-sm rounded bg-gujgov-600 hover:bg-gujgov-700 text-white disabled:opacity-50">
              {saving ? 'Saving…' : 'Save changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function TextField({ label, ...props }) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-500 mb-1">{label}</label>
      <input {...props} className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm" />
    </div>
  )
}

function SelectField({ label, value, onChange, options }) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-500 mb-1">{label}</label>
      <select value={value} onChange={onChange} className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm">
        {(options || []).map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  )
}
