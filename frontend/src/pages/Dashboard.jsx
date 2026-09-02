import React, { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts'
import api from '../api.js'
import { Card, StatCard, Spinner, ErrorBanner } from '../components/ui.jsx'

const PIE_COLORS = ['#2563eb', '#f97316', '#16a34a', '#dc2626', '#9333ea', '#0891b2']

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api
      .get('/stats/dashboard')
      .then((res) => setStats(res.data))
      .catch((e) => setError(e.response?.data?.detail || 'Failed to load dashboard stats'))
  }, [])

  if (error) return <ErrorBanner message={error} />
  if (!stats) return <Spinner />

  const departmentData = Object.entries(stats.by_department).map(([name, value]) => ({ name, value }))
  const cameraTypeData = Object.entries(stats.by_camera_type).map(([name, value]) => ({ name, value }))
  const districtData = Object.entries(stats.by_district)
    .sort((a, b) => b[1] - a[1])
    .map(([name, value]) => ({ name, value }))
  const yearData = Object.entries(stats.by_install_year).map(([name, value]) => ({ name, value }))

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard label="Total Cameras" value={stats.total_cameras} accent="text-gujgov-700" />
        <StatCard label="Online" value={stats.online} accent="text-green-600" />
        <StatCard label="Offline" value={stats.offline} accent="text-red-600" />
        <StatCard label="Maintenance" value={stats.maintenance} accent="text-amber-600" />
        <StatCard label="Ageing (7+ yrs)" value={stats.ageing} accent="text-purple-600" />
        <StatCard label="Synthetic / Demo" value={stats.synthetic} accent="text-slate-500" sub="Flagged demo data" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <h3 className="font-semibold text-slate-700 mb-3">Cameras by Department</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={departmentData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-15} textAnchor="end" height={60} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="value" fill="#2563eb" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card>
          <h3 className="font-semibold text-slate-700 mb-3">Cameras by Type</h3>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={cameraTypeData} dataKey="value" nameKey="name" outerRadius={90} label>
                {cameraTypeData.map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Legend />
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </Card>

        <Card className="lg:col-span-2">
          <h3 className="font-semibold text-slate-700 mb-3">Top Districts by Camera Count</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={districtData} layout="vertical" margin={{ left: 40 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" allowDecimals={false} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={140} />
              <Tooltip />
              <Bar dataKey="value" fill="#16a34a" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card className="lg:col-span-2">
          <h3 className="font-semibold text-slate-700 mb-3">Installations by Year</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={yearData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="value" fill="#f97316" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>
    </div>
  )
}
