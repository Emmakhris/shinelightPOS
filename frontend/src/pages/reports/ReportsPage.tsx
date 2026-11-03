import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, downloadCsv, qs } from '../../api/client'
import type { PaystackCharge, ShiftReport } from '../../api/types'
import { ShiftReportDoc, printDoc } from '../../components/print'
import { toast } from '../../components/toast'
import { Badge, Button, Empty, Field, Loading, PageHeader, Stat, Tabs } from '../../components/ui'
import { METHOD_LABELS, dateTime, isoDate, money, qty, toNumber } from '../../lib/format'
import { useSettings } from '../../lib/hooks'

type Tab = 'overview' | 'products' | 'categories' | 'cashiers' | 'payments' | 'tax' | 'valuation' | 'z'

interface Summary extends ShiftReport {
  start: string
  end: string
  net_sales_after_refunds: string
  gross_profit: string
  gross_margin_percent: string
  expenses: string
  net_profit: string
  average_sale: string
  by_day: { date: string; count: number; total: string }[]
  by_hour: { hour: number; count: number; total: string }[]
}

interface LineRow { name: string; quantity: string; refunded_quantity: string; revenue: string; discount: string; tax: string; net: string; cost: string; profit: string }

function presets() {
  const today = new Date()
  const d = (offset: number) => { const x = new Date(today); x.setDate(x.getDate() + offset); return isoDate(x) }
  const monday = new Date(today); monday.setDate(today.getDate() - ((today.getDay() + 6) % 7))
  const first = new Date(today.getFullYear(), today.getMonth(), 1)
  const lastMonthStart = new Date(today.getFullYear(), today.getMonth() - 1, 1)
  const lastMonthEnd = new Date(today.getFullYear(), today.getMonth(), 0)
  return [
    { label: 'Today', start: d(0), end: d(0) },
    { label: 'Yesterday', start: d(-1), end: d(-1) },
    { label: 'This week', start: isoDate(monday), end: d(0) },
    { label: 'This month', start: isoDate(first), end: d(0) },
    { label: 'Last month', start: isoDate(lastMonthStart), end: isoDate(lastMonthEnd) },
  ]
}

export function ReportsPage() {
  const [tab, setTab] = useState<Tab>('overview')
  const [range, setRange] = useState({ start: isoDate(), end: isoDate() })
  const params = qs(range)
  const exportCsv = (path: string, name: string) => downloadCsv(`${path}${params}`, `${name}-${range.start}-to-${range.end}.csv`).catch(toast.error)

  return (
    <div>
      <PageHeader title="Reports" />
      {tab !== 'valuation' && tab !== 'z' && (
        <div className="card mb-4 flex flex-wrap items-end gap-3 p-3">
          <Field label="From"><input type="date" className="input" value={range.start} onChange={(e) => setRange({ ...range, start: e.target.value })} /></Field>
          <Field label="To"><input type="date" className="input" value={range.end} onChange={(e) => setRange({ ...range, end: e.target.value })} /></Field>
          <div className="flex flex-wrap gap-1">
            {presets().map((p) => (
              <Button key={p.label} size="sm" variant={range.start === p.start && range.end === p.end ? 'primary' : 'secondary'} onClick={() => setRange({ start: p.start, end: p.end })}>
                {p.label}
              </Button>
            ))}
          </div>
        </div>
      )}
      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: 'overview', label: 'Overview' },
          { value: 'products', label: 'Products' },
          { value: 'categories', label: 'Categories' },
          { value: 'cashiers', label: 'Staff' },
          { value: 'payments', label: 'Payments' },
          { value: 'tax', label: 'Tax (GRA)' },
          { value: 'valuation', label: 'Stock value' },
          { value: 'z', label: 'End of day' },
        ]}
      />
      {tab === 'overview' && <Overview params={params} onExport={() => exportCsv('/reports/summary/', 'sales-by-day')} />}
      {(tab === 'products' || tab === 'categories') && <LineReport kind={tab} params={params} onExport={() => exportCsv(`/reports/${tab}/`, `sales-by-${tab}`)} />}
      {tab === 'cashiers' && <Cashiers params={params} onExport={() => exportCsv('/reports/cashiers/', 'sales-by-staff')} />}
      {tab === 'payments' && (
        <div className="space-y-4">
          <Payments params={params} onExport={() => exportCsv('/reports/payments/', 'payments')} />
          <PaystackPayments params={params} />
        </div>
      )}
      {tab === 'tax' && <Tax params={params} onExport={() => exportCsv('/reports/tax/', 'tax')} />}
      {tab === 'valuation' && <Valuation />}
      {tab === 'z' && <EndOfDay />}
    </div>
  )
}

function Bars({ rows, label }: { rows: { key: string; value: number; sub?: string }[]; label: string }) {
  const max = Math.max(...rows.map((r) => r.value), 1)
  return (
    <div className="card p-4">
      <h3 className="mb-3 font-bold">{label}</h3>
      <div className="flex h-48 items-end gap-1 overflow-x-auto">
        {rows.map((r) => (
          <div key={r.key} className="flex min-w-[18px] flex-1 flex-col items-center justify-end" title={`${r.key}: ${money(r.value)}${r.sub ? ` · ${r.sub}` : ''}`}>
            <div className="w-full rounded-t bg-brand-400 transition-all hover:bg-brand-600" style={{ height: `${(r.value / max) * 100}%`, minHeight: r.value ? 2 : 0 }} />
            <div className="mt-1 whitespace-nowrap text-[10px] text-slate-500">{r.key}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function Overview({ params, onExport }: { params: string; onExport: () => void }) {
  const s = useQuery({ queryKey: ['report', 'summary', params], queryFn: () => api.get<Summary>(`/reports/summary/${params}`) }).data
  if (!s) return <Loading />
  const hours = s.by_hour.filter((h) => h.hour >= 6 && h.hour <= 23)
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Gross sales" value={money(s.gross_sales)} sub={`${s.sales_count} sales · avg ${money(s.average_sale)}`} />
        <Stat label="Net sales (ex tax, after refunds)" value={money(s.net_sales_after_refunds)} />
        <Stat label="Gross profit" value={money(s.gross_profit)} sub={`${s.gross_margin_percent}% margin`} tone={toNumber(s.gross_profit) < 0 ? 'bad' : 'good'} />
        <Stat label="Net profit (after expenses)" value={money(s.net_profit)} sub={`Expenses ${money(s.expenses)}`} tone={toNumber(s.net_profit) < 0 ? 'bad' : undefined} />
        <Stat label="Discounts given" value={money(s.discounts)} />
        <Stat label="Tax collected" value={money(s.tax)} />
        <Stat label="Refunds" value={money(s.refunds)} />
        <Stat label="Voided sales" value={s.voided_count} sub={money(s.voided_total)} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Bars label="Sales by day" rows={s.by_day.map((d) => ({ key: d.date.slice(5), value: toNumber(d.total), sub: `${d.count} sales` }))} />
        <Bars label="Sales by hour" rows={hours.map((h) => ({ key: `${h.hour}`, value: toNumber(h.total), sub: `${h.count} sales` }))} />
      </div>
      <div className="flex justify-end"><Button variant="secondary" onClick={onExport}>Export daily totals CSV</Button></div>
    </div>
  )
}

function LineReport({ kind, params, onExport }: { kind: 'products' | 'categories'; params: string; onExport: () => void }) {
  const rows = useQuery({ queryKey: ['report', kind, params], queryFn: () => api.get<LineRow[]>(`/reports/${kind}/${params}`) })
  return (
    <div className="card overflow-x-auto">
      <div className="flex justify-end p-2"><Button size="sm" variant="secondary" onClick={onExport}>Export CSV</Button></div>
      {rows.isLoading ? <Loading /> : (
        <table className="table">
          <thead><tr><th>{kind === 'products' ? 'Product' : 'Category'}</th><th className="text-right">Qty</th><th className="text-right">Refunded</th><th className="text-right">Revenue</th><th className="text-right">Discount</th><th className="text-right">Tax</th><th className="text-right">Cost</th><th className="text-right">Profit</th></tr></thead>
          <tbody>
            {rows.data?.map((r) => (
              <tr key={r.name}>
                <td className="font-semibold">{r.name}</td>
                <td className="text-right">{qty(r.quantity)}</td>
                <td className="text-right text-slate-500">{toNumber(r.refunded_quantity) ? qty(r.refunded_quantity) : ''}</td>
                <td className="text-right">{money(r.revenue)}</td>
                <td className="text-right">{money(r.discount)}</td>
                <td className="text-right">{money(r.tax)}</td>
                <td className="text-right">{money(r.cost)}</td>
                <td className={`text-right font-semibold ${toNumber(r.profit) < 0 ? 'text-red-600' : ''}`}>{money(r.profit)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {rows.data?.length === 0 && <Empty>No sales in this period.</Empty>}
    </div>
  )
}

function Cashiers({ params, onExport }: { params: string; onExport: () => void }) {
  const rows = useQuery({
    queryKey: ['report', 'cashiers', params],
    queryFn: () => api.get<{ name: string; sales_count: number; total: string; discounts: string; refunds: string; voids: number }[]>(`/reports/cashiers/${params}`),
  })
  return (
    <div className="card overflow-x-auto">
      <div className="flex justify-end p-2"><Button size="sm" variant="secondary" onClick={onExport}>Export CSV</Button></div>
      <table className="table">
        <thead><tr><th>Staff</th><th className="text-right">Sales</th><th className="text-right">Total</th><th className="text-right">Discounts</th><th className="text-right">Refunds</th><th className="text-right">Voids</th></tr></thead>
        <tbody>
          {rows.data?.map((r) => (
            <tr key={r.name}><td className="font-semibold">{r.name}</td><td className="text-right">{r.sales_count}</td><td className="text-right">{money(r.total)}</td><td className="text-right">{money(r.discounts)}</td><td className="text-right">{money(r.refunds)}</td><td className="text-right">{r.voids}</td></tr>
          ))}
        </tbody>
      </table>
      {rows.data?.length === 0 && <Empty>No sales in this period.</Empty>}
    </div>
  )
}

function Payments({ params, onExport }: { params: string; onExport: () => void }) {
  const data = useQuery({
    queryKey: ['report', 'payments', params],
    queryFn: () => api.get<{ methods: { method: string; count: number; total: string; refunds: string; net: string }[]; momo_networks: { network: string; count: number; total: string }[] }>(`/reports/payments/${params}`),
  }).data
  if (!data) return <Loading />
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="card overflow-x-auto">
        <div className="flex items-center justify-between p-3"><h3 className="font-bold">By payment method</h3><Button size="sm" variant="secondary" onClick={onExport}>Export CSV</Button></div>
        <table className="table">
          <thead><tr><th>Method</th><th className="text-right">Count</th><th className="text-right">Taken</th><th className="text-right">Refunded</th><th className="text-right">Net</th></tr></thead>
          <tbody>
            {data.methods.map((m) => (
              <tr key={m.method}><td className="font-semibold">{METHOD_LABELS[m.method] ?? m.method}</td><td className="text-right">{m.count}</td><td className="text-right">{money(m.total)}</td><td className="text-right">{money(m.refunds)}</td><td className="text-right font-semibold">{money(m.net)}</td></tr>
            ))}
          </tbody>
        </table>
        {data.methods.length === 0 && <Empty>No payments.</Empty>}
      </div>
      <div className="card overflow-x-auto">
        <h3 className="p-3 font-bold">Mobile Money by network</h3>
        <table className="table">
          <thead><tr><th>Network</th><th className="text-right">Count</th><th className="text-right">Total</th></tr></thead>
          <tbody>
            {data.momo_networks.map((n) => <tr key={n.network}><td>{n.network.toUpperCase()}</td><td className="text-right">{n.count}</td><td className="text-right">{money(n.total)}</td></tr>)}
          </tbody>
        </table>
        {data.momo_networks.length === 0 && <Empty>No MoMo payments.</Empty>}
      </div>
    </div>
  )
}

/** Every MoMo prompt sent through Paystack, so money received without a finished sale stands out. */
function PaystackPayments({ params }: { params: string }) {
  const settings = useSettings().data
  const charges = useQuery({
    queryKey: ['report', 'paystack', params],
    queryFn: () => api.get<PaystackCharge[]>(`/payments/momo/${params}`),
    enabled: !!settings?.paystack_mode,
  })
  if (!settings?.paystack_mode) return null
  const recheck = async (ref: string) => {
    try {
      await api.get(`/payments/momo/${ref}/?force=1`)
      charges.refetch()
    } catch (err) {
      toast.error(err)
    }
  }
  const unmatched = (charges.data ?? []).filter((c) => c.status === 'success' && !c.invoice_number)
  return (
    <div className="card overflow-x-auto">
      <div className="flex flex-wrap items-center justify-between gap-2 p-3">
        <h3 className="font-bold">Paystack MoMo prompts</h3>
        {unmatched.length > 0 && (
          <span className="rounded bg-red-50 px-2 py-1 text-sm font-semibold text-red-700">
            {unmatched.length} paid but not on a sale ({money(unmatched.reduce((s, c) => s + toNumber(c.amount), 0))}). Refund the customer or record the sale.
          </span>
        )}
      </div>
      <table className="table">
        <thead><tr><th>When</th><th>Phone</th><th>Network</th><th className="text-right">Amount</th><th>Status</th><th>Sale</th><th>Cashier</th><th></th></tr></thead>
        <tbody>
          {charges.data?.map((c) => (
            <tr key={c.reference}>
              <td className="whitespace-nowrap">{dateTime(c.created_at)}</td>
              <td>{c.phone}</td>
              <td className="uppercase">{c.network}</td>
              <td className="text-right">{money(c.amount)}</td>
              <td>
                <Badge color={c.status === 'success' ? 'green' : c.status === 'failed' ? 'red' : 'amber'}>{c.status_label}</Badge>
                {c.message && c.status !== 'success' && <div className="text-xs text-slate-500">{c.message}</div>}
              </td>
              <td>{c.invoice_number ?? (c.status === 'success' ? <Badge color="red">Not on a sale</Badge> : '')}</td>
              <td>{c.created_by_name}</td>
              <td className="text-right">{c.status !== 'success' && <Button size="sm" variant="ghost" onClick={() => recheck(c.reference)}>Recheck</Button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {charges.data?.length === 0 && <Empty>No Paystack MoMo prompts in this period.</Empty>}
    </div>
  )
}

function Tax({ params, onExport }: { params: string; onExport: () => void }) {
  const data = useQuery({
    queryKey: ['report', 'tax', params],
    queryFn: () => api.get<{ taxes: { code: string; name: string; rate: string; collected: string; refunded: string; net: string }[]; total_collected: string; total_refunded: string; net_tax: string; standard_rated_net: string; zero_rated: string; exempt: string }>(`/reports/tax/${params}`),
  }).data
  if (!data) return <Loading />
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Standard-rated sales (ex tax)" value={money(data.standard_rated_net)} />
        <Stat label="Zero-rated sales" value={money(data.zero_rated)} />
        <Stat label="Exempt sales" value={money(data.exempt)} />
        <Stat label="Net tax payable" value={money(data.net_tax)} />
      </div>
      <div className="card overflow-x-auto">
        <div className="flex items-center justify-between p-3"><h3 className="font-bold">Taxes and levies</h3><Button size="sm" variant="secondary" onClick={onExport}>Export CSV</Button></div>
        <table className="table">
          <thead><tr><th>Tax</th><th className="text-right">Rate</th><th className="text-right">Collected</th><th className="text-right">Refunded</th><th className="text-right">Net</th></tr></thead>
          <tbody>
            {data.taxes.map((t) => <tr key={t.code}><td className="font-semibold">{t.name}</td><td className="text-right">{Number(t.rate)}%</td><td className="text-right">{money(t.collected)}</td><td className="text-right">{money(t.refunded)}</td><td className="text-right font-semibold">{money(t.net)}</td></tr>)}
          </tbody>
        </table>
        {data.taxes.length === 0 && <Empty>No tax collected in this period.</Empty>}
      </div>
      <p className="text-xs text-slate-500">Use this as a working figure for your VAT return. Confirm rates and filing rules with GRA or your accountant.</p>
    </div>
  )
}

function Valuation() {
  const data = useQuery({
    queryKey: ['report', 'valuation'],
    queryFn: () => api.get<{ items: { name: string; category: string; quantity: string; cost_price: string; price: string; cost_value: string; retail_value: string }[]; cost_value: string; retail_value: string; potential_profit: string }>('/reports/inventory-valuation/'),
  }).data
  if (!data) return <Loading />
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Stock value at cost" value={money(data.cost_value)} />
        <Stat label="Stock value at selling price" value={money(data.retail_value)} />
        <Stat label="Potential profit" value={money(data.potential_profit)} tone="good" />
      </div>
      <div className="card overflow-x-auto">
        <div className="flex justify-end p-2"><Button size="sm" variant="secondary" onClick={() => downloadCsv('/reports/inventory-valuation/', 'stock-value.csv').catch(toast.error)}>Export CSV</Button></div>
        <table className="table">
          <thead><tr><th>Item</th><th>Category</th><th className="text-right">Qty</th><th className="text-right">Cost</th><th className="text-right">Value at cost</th><th className="text-right">Value at price</th></tr></thead>
          <tbody>
            {data.items.map((i) => <tr key={i.name}><td>{i.name}</td><td>{i.category}</td><td className="text-right">{qty(i.quantity)}</td><td className="text-right">{money(i.cost_price)}</td><td className="text-right">{money(i.cost_value)}</td><td className="text-right">{money(i.retail_value)}</td></tr>)}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function EndOfDay() {
  const settings = useSettings().data
  const [date, setDate] = useState(isoDate())
  const report = useQuery({
    queryKey: ['report', 'z', date],
    queryFn: () => api.get<ShiftReport & { date: string; shifts: { id: number; cashier: string; register_name: string; status: string; opened_at: string; closed_at: string | null; expected_cash: string | null; counted_cash: string | null; difference: string | null }[] }>(`/reports/z/?date=${date}`),
  })
  const r = report.data
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <div>
        <div className="mb-3 flex items-end gap-2">
          <Field label="Day"><input type="date" className="input" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
          {r && settings && <Button onClick={() => printDoc(<ShiftReportDoc report={r} settings={settings} title={`END OF DAY ${date}`} />, settings.receipt_width)}>🖨 Print</Button>}
        </div>
        <div className="card overflow-x-auto">
          <h3 className="p-3 font-bold">Tills / shifts</h3>
          <table className="table">
            <thead><tr><th>Cashier</th><th>Till</th><th>Opened</th><th>Closed</th><th className="text-right">Expected</th><th className="text-right">Counted</th><th className="text-right">Over/short</th></tr></thead>
            <tbody>
              {r?.shifts.map((s) => (
                <tr key={s.id}><td>{s.cashier}</td><td>{s.register_name}</td><td>{dateTime(s.opened_at)}</td><td>{s.closed_at ? dateTime(s.closed_at) : 'open'}</td><td className="text-right">{s.expected_cash ? money(s.expected_cash) : ''}</td><td className="text-right">{s.counted_cash ? money(s.counted_cash) : ''}</td><td className={`text-right font-semibold ${toNumber(s.difference) < 0 ? 'text-red-600' : ''}`}>{s.difference ? money(s.difference) : ''}</td></tr>
              ))}
            </tbody>
          </table>
          {r?.shifts.length === 0 && <Empty>No shifts on this day.</Empty>}
        </div>
      </div>
      <div className="rounded border border-slate-200 bg-white">{r && settings ? <ShiftReportDoc report={r} settings={settings} title={`END OF DAY ${date}`} /> : <Loading />}</div>
    </div>
  )
}
