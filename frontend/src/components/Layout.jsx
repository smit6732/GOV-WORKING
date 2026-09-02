import React from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

const ALL_TABS = [
  { to: '/', label: 'Dashboard', roles: ['super_admin', 'department_admin', 'viewer'] },
  { to: '/map', label: 'GIS Map', roles: ['super_admin', 'department_admin', 'viewer'] },
  { to: '/registry', label: 'Camera Registry', roles: ['super_admin', 'department_admin', 'viewer'] },
  { to: '/add-camera', label: 'Add Camera', roles: ['super_admin', 'department_admin'] },
  { to: '/bulk-upload', label: 'Bulk Upload', roles: ['super_admin', 'department_admin'] },
  { to: '/health', label: 'Health', roles: ['super_admin', 'department_admin', 'viewer'] },
  { to: '/coverage', label: 'Coverage & Gap Analysis', roles: ['super_admin', 'department_admin', 'viewer'] },
  { to: '/audit-logs', label: 'Audit Logs', roles: ['super_admin', 'department_admin'] },
]

const ROLE_LABELS = {
  super_admin: 'Super Admin',
  department_admin: 'Department Admin',
  viewer: 'Viewer',
}

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const tabs = ALL_TABS.filter((t) => user && t.roles.includes(user.role))

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <header className="bg-gujgov-900 text-white shadow">
        <div className="px-4 py-3 flex items-center justify-between flex-wrap gap-2">
          <div>
            <h1 className="text-lg font-semibold leading-tight">
              Gujarat CCTV GIS Registry
            </h1>
            <p className="text-xs text-blue-200">
              Centralised metadata &amp; asset visibility layer — not a live surveillance system
            </p>
          </div>
          {user && (
            <div className="flex items-center gap-3 text-sm">
              <div className="text-right">
                <div className="font-medium">{user.full_name}</div>
                <div className="text-blue-200 text-xs">
                  {ROLE_LABELS[user.role]}
                  {user.department ? ` · ${user.department}` : ''}
                </div>
              </div>
              <button
                onClick={handleLogout}
                className="bg-gujgov-accent hover:bg-orange-600 px-3 py-1.5 rounded text-white text-sm font-medium"
              >
                Logout
              </button>
            </div>
          )}
        </div>
        <nav className="bg-gujgov-800 overflow-x-auto">
          <div className="flex px-2">
            {tabs.map((t) => (
              <NavLink
                key={t.to}
                to={t.to}
                end={t.to === '/'}
                className={({ isActive }) =>
                  `whitespace-nowrap px-4 py-2.5 text-sm font-medium border-b-2 ${
                    isActive
                      ? 'border-gujgov-accent text-white'
                      : 'border-transparent text-blue-200 hover:text-white hover:border-blue-300'
                  }`
                }
              >
                {t.label}
              </NavLink>
            ))}
          </div>
        </nav>
      </header>
      <main className="flex-1 p-4 max-w-[1600px] w-full mx-auto">
        <Outlet />
      </main>
      <footer className="text-center text-xs text-slate-400 py-3">
        Demo registry — synthetic camera data flagged <code>is_synthetic=true</code>. Not connected to any live feed.
      </footer>
    </div>
  )
}
