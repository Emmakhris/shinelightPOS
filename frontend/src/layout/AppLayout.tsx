import { useState, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useCurrentShift, useSettings } from '../lib/hooks'
import { useAuth } from '../stores/auth'

interface NavItem {
  to: string
  label: string
  icon: string
  show: boolean
}

export function AppLayout({ children }: { children: ReactNode }) {
  const { user, can, lock, logout } = useAuth()
  const settings = useSettings().data
  const shift = useCurrentShift().data
  const [open, setOpen] = useState(false)
  const location = useLocation()
  // The register and order screens use the full height of the screen.
  const fullBleed = location.pathname === '/pos' || location.pathname.startsWith('/tables/order')

  const nav: NavItem[] = [
    { to: '/', label: 'Dashboard', icon: '◧', show: can('view_reports') },
    { to: '/pos', label: 'Register', icon: '🛒', show: !!settings?.retail_mode && can('sell') },
    { to: '/tables', label: 'Tables', icon: '🍽', show: !!settings?.restaurant_mode && can('sell') },
    { to: '/sales', label: 'Sales', icon: '🧾', show: can('sell') },
    { to: '/shifts', label: 'Shifts', icon: '⏱', show: can('sell') },
    { to: '/customers', label: 'Customers', icon: '👥', show: can('sell') },
    { to: '/products', label: 'Products', icon: '📦', show: can('manage_catalog') },
    { to: '/inventory', label: 'Inventory', icon: '🏷', show: can('manage_inventory') },
    { to: '/reports', label: 'Reports', icon: '📈', show: can('view_reports') },
    { to: '/users', label: 'Staff', icon: '🔑', show: can('manage_users') || can('view_audit') },
    { to: '/settings', label: 'Settings', icon: '⚙', show: can('manage_settings') || can('manage_tables') },
  ]

  return (
    <div className="flex h-full">
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-56 flex-col bg-slate-900 text-slate-200 transition-transform lg:static lg:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center gap-2 px-4 py-4">
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-500 text-lg font-black text-white">S</span>
          <div className="min-w-0">
            <div className="truncate text-sm font-bold text-white">{settings?.name ?? 'ShineLight POS'}</div>
            <div className="text-xs text-slate-400">ShineLight POS</div>
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2">
          {nav.filter((n) => n.show).map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === '/'}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
                  isActive ? 'bg-brand-500 text-white' : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`
              }
            >
              <span className="w-5 text-center">{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-800 p-3">
          <div className="mb-2 px-1">
            <div className="truncate text-sm font-semibold text-white">{user?.display_name}</div>
            <div className="text-xs capitalize text-slate-400">
              {user?.role} · {shift ? <span className="text-emerald-400">shift open</span> : 'no shift'}
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={lock} className="flex-1 rounded-lg bg-slate-800 px-2 py-2 text-xs font-semibold hover:bg-slate-700" title="Switch cashier">
              🔒 Lock
            </button>
            <button onClick={logout} className="flex-1 rounded-lg bg-slate-800 px-2 py-2 text-xs font-semibold hover:bg-slate-700">
              Sign out
            </button>
          </div>
        </div>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/40 lg:hidden" onClick={() => setOpen(false)} />}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-2 lg:hidden">
          <button onClick={() => setOpen(true)} className="rounded-lg p-2 text-xl hover:bg-slate-100" aria-label="Menu">
            ☰
          </button>
          <span className="font-bold">{settings?.name}</span>
        </header>
        <main className={`min-h-0 flex-1 ${fullBleed ? 'overflow-hidden' : 'overflow-y-auto p-4 lg:p-6'}`}>{children}</main>
      </div>
    </div>
  )
}
