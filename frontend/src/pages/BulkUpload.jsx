import React, { useState } from 'react'
import api from '../api.js'
import { Card, ErrorBanner, Spinner } from '../components/ui.jsx'

export default function BulkUpload() {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [result, setResult] = useState(null)

  const handlePreview = async (e) => {
    e.preventDefault()
    if (!file) return
    setLoading(true)
    setError(null)
    setPreview(null)
    setResult(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await api.post('/cameras/bulk-upload/preview', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setPreview(res.data)
    } catch (e2) {
      setError(e2.response?.data?.detail || 'Failed to validate file')
    } finally {
      setLoading(false)
    }
  }

  const handleCommit = async () => {
    if (!preview) return
    setCommitting(true)
    setError(null)
    try {
      const res = await api.post('/cameras/bulk-upload/commit', { rows: preview.all_valid_rows })
      setResult(res.data)
      setPreview(null)
      setFile(null)
    } catch (e2) {
      setError(e2.response?.data?.detail || 'Commit failed')
    } finally {
      setCommitting(false)
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <h2 className="text-lg font-semibold mb-1">Bulk Camera Upload</h2>
        <p className="text-sm text-slate-500 mb-4">
          Upload a CSV of camera metadata (same columns as <code>demo_cctv_cameras.csv</code>). Rows are validated
          and previewed before anything is written to the registry.
        </p>
        <ErrorBanner message={error} />
        <form onSubmit={handlePreview} className="flex items-center gap-3">
          <input
            type="file"
            accept=".csv"
            onChange={(e) => setFile(e.target.files[0])}
            className="text-sm"
          />
          <button
            type="submit"
            disabled={!file || loading}
            className="px-4 py-2 rounded bg-gujgov-600 hover:bg-gujgov-700 text-white text-sm font-medium disabled:opacity-50"
          >
            {loading ? 'Validating…' : 'Validate & Preview'}
          </button>
        </form>
      </Card>

      {loading && <Spinner />}

      {result && (
        <Card className="bg-green-50 border border-green-200">
          <p className="text-green-700 text-sm font-medium">
            Upload committed: {result.inserted} camera(s) inserted, {result.skipped_duplicates} skipped as duplicates / out-of-scope.
          </p>
        </Card>
      )}

      {preview && (
        <Card>
          <div className="grid grid-cols-4 gap-3 mb-4 text-center">
            <SummaryStat label="Total Rows" value={preview.total_rows} />
            <SummaryStat label="Valid" value={preview.valid_count} accent="text-green-600" />
            <SummaryStat label="Invalid" value={preview.invalid_count} accent="text-red-600" />
            <SummaryStat label="Dup. IDs in DB" value={preview.duplicate_camera_ids_in_db} accent="text-amber-600" />
          </div>

          <h3 className="font-medium text-sm text-slate-700 mb-2">
            Preview — first {preview.preview_valid_rows.length} valid rows
          </h3>
          <div className="overflow-x-auto mb-4">
            <table className="min-w-full text-xs border">
              <thead className="bg-slate-100">
                <tr>
                  {['camera_id', 'district', 'department', 'camera_type', 'vendor', 'connectivity_status', 'latitude', 'longitude'].map((h) => (
                    <th key={h} className="px-2 py-1 text-left border-b">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.preview_valid_rows.map((r, i) => (
                  <tr key={i} className="border-b">
                    <td className="px-2 py-1">{r.camera_id || '(auto)'}</td>
                    <td className="px-2 py-1">{r.district}</td>
                    <td className="px-2 py-1">{r.department}</td>
                    <td className="px-2 py-1">{r.camera_type}</td>
                    <td className="px-2 py-1">{r.vendor}</td>
                    <td className="px-2 py-1">{r.connectivity_status}</td>
                    <td className="px-2 py-1">{r.latitude}</td>
                    <td className="px-2 py-1">{r.longitude}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {preview.errors.length > 0 && (
            <details className="mb-4">
              <summary className="cursor-pointer text-sm font-medium text-red-600">
                {preview.errors.length} row error(s) — click to expand
              </summary>
              <div className="overflow-x-auto mt-2 max-h-64 overflow-y-auto">
                <table className="min-w-full text-xs border">
                  <thead className="bg-red-50">
                    <tr>
                      <th className="px-2 py-1 text-left border-b">Row #</th>
                      <th className="px-2 py-1 text-left border-b">Errors</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.errors.map((e, i) => (
                      <tr key={i} className="border-b align-top">
                        <td className="px-2 py-1">{e.row_number || '—'}</td>
                        <td className="px-2 py-1 text-red-700">{e.errors.join('; ')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}

          <div className="flex justify-end">
            <button
              onClick={handleCommit}
              disabled={committing || preview.valid_count === 0}
              className="px-5 py-2 rounded bg-green-600 hover:bg-green-700 text-white text-sm font-medium disabled:opacity-50"
            >
              {committing ? 'Committing…' : `Commit ${preview.valid_count} Valid Rows`}
            </button>
          </div>
        </Card>
      )}
    </div>
  )
}

function SummaryStat({ label, value, accent = 'text-slate-800' }) {
  return (
    <div>
      <div className={`text-2xl font-bold ${accent}`}>{value}</div>
      <div className="text-xs text-slate-500">{label}</div>
    </div>
  )
}
