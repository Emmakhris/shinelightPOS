import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { PageHeader, Stat } from '../components/ui'
import { money, qty, toNumber } from '../lib/format'
import { useSettings } from '../lib/hooks'

interface Dashboard {
  today: { count: number; total: string }
  yesterday: { count: number; total: string }
  low_stock_count?: number
  open_shifts?: number
  open_orders?: number
  customers_owing?: string
  top_products?: { name: string; quantity: string; revenue: string }[]
  last_backup_at?: string | null
}

const BACKUP_WARNING_HOURS = 48

export function DashboardPage() {
  const settings = useSettings().data
  const data = useQuery({ queryKey: ['dashboard'], queryFn: () => api.get<Dashboard>('/reports/dashboard/'), refetchInterval: 60_000 }).data
  const today = toNumber(data?.today.total)
  const yesterday = toNumber(data?.yesterday.total)
  const change = yesterday ? Math.round(((today - yesterday) / yesterday) * 100) : null
  const backupAgeHours = data?.last_backup_at ? (Date.now() - new Date(data.last_backup_at).getTime()) / 3_600_000 : null
  const backupWarning = data && data.last_backup_at !== undefined && (backupAgeHours === null || backupAgeHours > BACKUP_WARNING_HOURS)

  return (
    <div>
      <PageHeader title={`Good ${greeting()}!`} subtitle={settings?.name} />
      {backupWarning && (
        <Link to="/settings" className="mb-4 block rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 hover:bg-red-100">
          <b>{backupAgeHours === null ? 'No backup has been made yet.' : `The last backup was ${Math.floor(backupAgeHours / 24)} days ago.`}</b>{' '}
          If this computer fails, your sales and stock records could be lost. Open Settings → Backups.
        </Link>
      )}
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Sales today"
          value={money(today)}
          sub={change === null ? `${data?.today.count ?? 0} sales` : `${data?.today.count ?? 0} sales · ${change >= 0 ? '▲' : '▼'} ${Math.abs(change)}% vs yesterday`}
        />
        <Stat label="Average sale" value={money(data?.today.count ? today / data.today.count : 0)} />
        <Link to="/inventory">
          <Stat label="Low stock items" value={data?.low_stock_count ?? 0} tone={data?.low_stock_count ? 'bad' : undefined} sub="Tap to view inventory" />
        </Link>
        <Link to="/customers">
          <Stat label="Owed by customers" value={money(data?.customers_owing)} />
        </Link>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="card p-4 lg:col-span-2">
          <h2 className="mb-3 font-bold">Top products today</h2>
          {data?.top_products?.length ? (
            <table className="table">
              <thead>
                <tr><th>Product</th><th className="text-right">Qty</th><th className="text-right">Revenue</th></tr>
              </thead>
              <tbody>
                {data.top_products.map((p) => (
                  <tr key={p.name}><td>{p.name}</td><td className="text-right">{qty(p.quantity)}</td><td className="text-right">{money(p.revenue)}</td></tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-slate-500">No sales yet today.</p>
          )}
        </div>
        <div className="card space-y-3 p-4">
          <h2 className="font-bold">Right now</h2>
          <div className="flex justify-between text-sm"><span>Open shifts</span><b>{data?.open_shifts ?? 0}</b></div>
          {settings?.restaurant_mode && <div className="flex justify-between text-sm"><span>Open table orders</span><b>{data?.open_orders ?? 0}</b></div>}
          <div className="grid gap-2 pt-2">
            {settings?.retail_mode && <Link to="/pos" className="rounded-lg bg-brand-500 px-4 py-3 text-center font-semibold text-white hover:bg-brand-600">Open register</Link>}
            {settings?.restaurant_mode && <Link to="/tables" className="rounded-lg bg-slate-800 px-4 py-3 text-center font-semibold text-white hover:bg-slate-900">Tables</Link>}
            <Link to="/reports" className="rounded-lg border border-slate-300 px-4 py-3 text-center font-semibold hover:bg-slate-50">Reports</Link>
          </div>
        </div>
      </div>
    </div>
  )
}

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'morning' : h < 17 ? 'afternoon' : 'evening'
}
