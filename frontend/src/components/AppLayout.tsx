import { NavLink, Outlet } from 'react-router-dom'
import { Activity, Boxes, LayoutDashboard, LogOut, Server } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'

const NAV_ITEMS = [
  { to: '/', label: 'Executive', icon: LayoutDashboard, end: true },
  { to: '/infrastructure', label: 'Infrastructure', icon: Server },
  { to: '/kubernetes', label: 'Kubernetes', icon: Boxes },
]

export function AppLayout() {
  const { user, logout } = useAuth()

  return (
    <div className="flex h-screen bg-bg text-text-primary">
      <aside className="flex w-56 flex-col border-r border-border bg-surface">
        <div className="flex items-center gap-2 border-b border-border px-4 py-4">
          <Activity className="h-5 w-5 text-accent" />
          <span className="font-mono text-sm font-semibold tracking-tight">platform</span>
        </div>

        <nav className="flex-1 space-y-1 p-3">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? 'bg-accent/10 text-accent'
                    : 'text-text-secondary hover:bg-surface-hover hover:text-text-primary'
                }`
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-border p-3">
          <div className="mb-2 truncate text-xs text-text-muted">{user?.email}</div>
          <button
            onClick={() => logout()}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-text-secondary hover:bg-surface-hover hover:text-text-primary"
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </button>
        </div>
      </aside>

      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex items-center justify-between border-b border-border px-6 py-3">
          <div className="flex items-center gap-2 text-sm text-text-secondary">
            {/* Signature element: live pulse — reinforces "this platform is
                actively monitoring something right now," not a static badge. */}
            <span className="relative flex h-2 w-2">
              <span className="pulse-live absolute inline-flex h-2 w-2 rounded-full bg-accent" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
            </span>
            System live
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
