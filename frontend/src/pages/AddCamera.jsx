import React, { useEffect, useState } from 'react'
import api from '../api.js'
import { useAuth } from '../context/AuthContext.jsx'
import { Card, ErrorBanner } from '../components/ui.jsx'

const EMPTY = {
  district: '',
  department: '',
  nearest_station: '',
  camera_type: '',
  vendor: '',
  ownership: 'Government',
  latitude: '',
  longitude: '',
  storage_type: '',
  retention_days: 30,
  install_year: new Date().getFullYear(),
  connectivity_status: 'Active',
}

export default function AddCamera() {
  const { user } = useAuth()
  const [options, setOptions] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.get('/cameras/meta/options').then((res) => {
      setOptions(res.data)
      setForm((f) => ({
        ...f,
        department: user.role === 'department_admin' ? user.department : res.data.departments[0],
        camera_type: res.data.camera_types[0],
        vendor: res.data.vendors[0],
        storage_type: res.data.storage_types[0],
      }))
    })
  }, [])

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      const res = await api.post('/cameras', {
        ...form,
        latitude: parseFloat(form.latitude),
        longitude: parseFloat(form.longitude),
        retention_days: form.retention_days ? parseInt(form.retention_days) : null,
        install_year: form.install_year ? parseInt(form.install_year) : null,
      })
      setSuccess(`Camera ${res.data.camera_id} created successfully.`)
      setForm((f) => ({ ...EMPTY, department: f.department, camera_type: f.camera_type, vendor: f.vendor, storage_type: f.storage_type }))
    } catch (e2) {
      setError(e2.response?.data?.detail || 'Failed to create camera')
    } finally {
      setSaving(false)
    }
  }

  if (!options) return null

  return (
    <Card className="max-w-3xl mx-auto">
      <h2 className="text-lg font-semibold mb-1">Add Camera</h2>
      <p className="text-sm text-slate-500 mb-4">Register a new CCTV asset's metadata and location. No video feed or credentials are stored.</p>

      <ErrorBanner message={error} />
      {success && <div className="bg-green-50 border border-green-200 text-green-700 text-sm rounded p-3 mb-3">{success}</div>}

      <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <TextField label="District" required value={form.district} onChange={set('district')} placeholder="e.g. Ahmedabad City" />
        <SelectField
          label="Department"
          value={form.department}
          onChange={set('department')}
          options={user.role === 'department_admin' ? [user.department] : options.departments}
          disabled={user.role === 'department_admin'}
        />
        <TextField label="Nearest Station" value={form.nearest_station} onChange={set('nearest_station')} placeholder="e.g. Airport" />
        <SelectField label="Camera Type" value={form.camera_type} onChange={set('camera_type')} options={options.camera_types} />
        <SelectField label="Vendor" value={form.vendor} onChange={set('vendor')} options={options.vendors} />
        <SelectField label="Ownership" value={form.ownership} onChange={set('ownership')} options={options.ownership_types} />
        <TextField label="Latitude" type="number" step="any" required value={form.latitude} onChange={set('latitude')} placeholder="20.19 – 24.9" />
        <TextField label="Longitude" type="number" step="any" required value={form.longitude} onChange={set('longitude')} placeholder="68.0 – 74.6" />
        <SelectField label="Storage Type" value={form.storage_type} onChange={set('storage_type')} options={options.storage_types} />
        <TextField label="Retention (days)" type="number" value={form.retention_days} onChange={set('retention_days')} />
        <TextField label="Install Year" type="number" value={form.install_year} onChange={set('install_year')} />
        <SelectField label="Connectivity Status" value={form.connectivity_status} onChange={set('connectivity_status')} options={options.connectivity_statuses} />

        <div className="md:col-span-2 flex justify-end">
          <button type="submit" disabled={saving} className="px-5 py-2 rounded bg-gujgov-600 hover:bg-gujgov-700 text-white text-sm font-medium disabled:opacity-50">
            {saving ? 'Saving…' : 'Add Camera'}
          </button>
        </div>
      </form>
    </Card>
  )
}

function TextField({ label, required, ...props }) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-500 mb-1">{label}{required && ' *'}</label>
      <input {...props} required={required} className="w-full border border-slate-300 rounded px-3 py-2 text-sm" />
    </div>
  )
}

function SelectField({ label, value, onChange, options, disabled }) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-500 mb-1">{label}</label>
      <select value={value} onChange={onChange} disabled={disabled} className="w-full border border-slate-300 rounded px-3 py-2 text-sm disabled:bg-slate-100">
        {(options || []).map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  )
}
