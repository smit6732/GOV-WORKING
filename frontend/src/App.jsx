import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import { RequireAuth, RequireRole } from './components/ProtectedRoute.jsx'
import Login from './pages/Login.jsx'
import Dashboard from './pages/Dashboard.jsx'
import GISMap from './pages/GISMap.jsx'
import CameraRegistry from './pages/CameraRegistry.jsx'
import AddCamera from './pages/AddCamera.jsx'
import BulkUpload from './pages/BulkUpload.jsx'
import Health from './pages/Health.jsx'
import Coverage from './pages/Coverage.jsx'
import AuditLogs from './pages/AuditLogs.jsx'
import VideoWall from './pages/VideoWall.jsx'
import VehicleSearch from './pages/VehicleSearch.jsx'
import Tags from './pages/Tags.jsx'
import Alerts from './pages/Alerts.jsx'

const ADMIN_ROLES = ['super_admin', 'department_admin']

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/map" element={<GISMap />} />
        <Route path="/registry" element={<CameraRegistry />} />
        <Route
          path="/add-camera"
          element={
            <RequireRole roles={ADMIN_ROLES}>
              <AddCamera />
            </RequireRole>
          }
        />
        <Route
          path="/bulk-upload"
          element={
            <RequireRole roles={ADMIN_ROLES}>
              <BulkUpload />
            </RequireRole>
          }
        />
        <Route path="/health" element={<Health />} />
        <Route path="/coverage" element={<Coverage />} />
        <Route
          path="/audit-logs"
          element={
            <RequireRole roles={ADMIN_ROLES}>
              <AuditLogs />
            </RequireRole>
          }
        />
        <Route path="/video-wall" element={<VideoWall />} />
        <Route path="/vehicle-search" element={<VehicleSearch />} />
        <Route
          path="/tags"
          element={
            <RequireRole roles={ADMIN_ROLES}>
              <Tags />
            </RequireRole>
          }
        />
        <Route path="/alerts" element={<Alerts />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
