import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { api, downloadCsv, qs } from '../../api/client'
import type { Paginated, PaymentMethod, Refund, Sale, SaleStatus, SaleSummary } from '../../api/types'
import { isCancelled, withApproval } from '../../components/approval'
import { ReceiptDoc, RefundDoc, printDoc } from '../../components/print'
import { toast } from '../../components/toast'
import { Badge, Button, Empty, Field, Loading, Modal, PageHeader, Toggle } from '../../components/ui'
import { METHOD_LABELS, ORDER_TYPE_LABELS, dateTime, isoDate, money, qty, toNumber } from '../../lib/format'
import { useRefreshAfterSale, useSettings } from '../../lib/hooks'
import { useAuth } from '../../stores/auth'

const STATUS_COLORS: Record<SaleStatus, 'green' | 'amber' | 'red' | 'gray'> = {
  completed: 'green',
  partially_refunded: 'amber',
  refunded: 'gray',
  voided: 'red',
}

export function SalesPage() {
  const [start, setStart] = useState(isoDate())
  const [end, setEnd] = useState(isoDate())
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [method, setMethod] = useState('')
  const [page, setPage] = useState(1)
  const [openId, setOpenId] = useState<number | null>(null)
  const can = useAuth((s) => s.can)

  const params = {
    created_at__gte: start ? `${start}T00:00:00` : undefined,
    created_at__lte: end ? `${end}T23:59:59` : undefined,
    search,
    status,
    payments__method: method,
  }
  const sales = useQuery({
    queryKey: ['sales', params, page],
    queryFn: () => api.get<Paginated<SaleSummary>>(`/sales/${qs({ ...params, page })}`),
    placeholderData: keepPreviousData,
  })

  return (
    <div>
      <PageHeader
        title="Sales"
        subtitle={can('view_reports') ? 'All sales' : 'Your sales'}
        actions={<Button variant="secondary" onClick={() => downloadCsv(`/sales/${qs(params)}`, `sales-${start}-to-${end}.csv`).catch(toast.error)}>Export CSV</Button>}
      />
      <div className="card mb-4 grid gap-3 p-3 sm:grid-cols-2 lg:grid-cols-5">
        <Field label="From"><input type="date" className="input" value={start} onChange={(e) => { setStart(e.target.value); setPage(1) }} /></Field>
        <Field label="To"><input type="date" className="input" value={end} onChange={(e) => { setEnd(e.target.value); setPage(1) }} /></Field>
        <Field label="Search"><input className="input" placeholder="Invoice, customer, MoMo ref" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} /></Field>
        <Field label="Status">
          <select className="input" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }}>
            <option value="">All</option>
            <option value="completed">Completed</option>
            <option value="partially_refunded">Partly refunded</option>
            <option value="refunded">Refunded</option>
            <option value="voided">Voided</option>
          </select>
        </Field>
        <Field label="Paid by">
          <select className="input" value={method} onChange={(e) => { setMethod(e.target.value); setPage(1) }}>
            <option value="">Any</option>
            {Object.entries(METHOD_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
      </div>
      <div className="card overflow-x-auto">
        {sales.isLoading ? <Loading /> : (
          <table className="table">
            <thead>
              <tr><th>Invoice</th><th>Date</th><th>Type</th><th>Cashier</th><th>Customer</th><th>Paid by</th><th>Status</th><th className="text-right">Total</th></tr>
            </thead>
            <tbody>
              {sales.data?.results.map((s) => (
                <tr key={s.id} className="cursor-pointer" onClick={() => setOpenId(s.id)}>
                  <td className="font-mono text-xs font-semibold">{s.invoice_number}</td>
                  <td>{dateTime(s.created_at)}</td>
                  <td>{ORDER_TYPE_LABELS[s.order_type]}{s.table_name && ` · ${s.table_name}`}</td>
                  <td>{s.cashier_name}</td>
                  <td>{s.customer_name ?? '—'}</td>
                  <td>{s.payment_methods.map((m: PaymentMethod) => METHOD_LABELS[m]).join(', ')}</td>
                  <td><Badge color={STATUS_COLORS[s.status]}>{s.status_label}</Badge></td>
                  <td className="text-right font-semibold">{money(s.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {sales.data?.count === 0 && <Empty>No sales in this period.</Empty>}
      </div>
      {sales.data && sales.data.count > 50 && (
        <div className="mt-3 flex items-center justify-end gap-2 text-sm">
          <Button variant="secondary" size="sm" disabled={!sales.data.previous} onClick={() => setPage(page - 1)}>Previous</Button>
          <span>Page {page} of {Math.ceil(sales.data.count / 50)}</span>
          <Button variant="secondary" size="sm" disabled={!sales.data.next} onClick={() => setPage(page + 1)}>Next</Button>
        </div>
      )}
      {openId && <SaleDetailModal id={openId} onClose={() => setOpenId(null)} />}
    </div>
  )
}

export function SaleDetailModal({ id, onClose }: { id: number; onClose: () => void }) {
  const settings = useSettings().data
  const qc = useQueryClient()
  const refresh = useRefreshAfterSale()
  const sale = useQuery({ queryKey: ['sale', id], queryFn: () => api.get<Sale>(`/sales/${id}/`) })
  const [refunding, setRefunding] = useState(false)
  const s = sale.data

  const reprint = () => s && settings && printDoc(<ReceiptDoc sale={s} settings={settings} copy />, settings.receipt_width)
  const voidSale = async () => {
    if (!s) return
    const reason = window.prompt('Why is this sale being voided?')
    if (!reason) return
    try {
      await withApproval((pin) => api.post(`/sales/${s.id}/void/`, { reason, approval_pin: pin }))
      toast.success('Sale voided')
      qc.invalidateQueries({ queryKey: ['sale', id] })
      refresh()
    } catch (err) {
      if (!isCancelled(err)) toast.error(err)
    }
  }

  return (
    <Modal
      open
      size="lg"
      onClose={onClose}
      title={s ? `Sale ${s.invoice_number}` : 'Sale'}
      footer={s && (
        <>
          {s.status === 'completed' && <Button variant="danger" className="mr-auto" onClick={voidSale}>Void</Button>}
          <Button variant="secondary" onClick={reprint}>🖨 Reprint</Button>
          {s.status !== 'voided' && s.status !== 'refunded' && <Button onClick={() => setRefunding(true)}>Refund…</Button>}
        </>
      )}
    >
      {!s ? <Loading /> : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
            <Info label="Date" value={dateTime(s.created_at)} />
            <Info label="Cashier" value={s.cashier_name} />
            <Info label="Customer" value={s.customer_name ?? 'Walk-in'} />
            <Info label="Status" value={<Badge color={STATUS_COLORS[s.status]}>{s.status_label}</Badge>} />
          </div>
          {s.status === 'voided' && <p className="rounded bg-red-50 p-2 text-sm text-red-700">Voided by {s.voided_by_name} on {dateTime(s.voided_at)}: {s.void_reason}</p>}
          <table className="table">
            <thead><tr><th>Item</th><th className="text-right">Qty</th><th className="text-right">Price</th><th className="text-right">Disc.</th><th className="text-right">Total</th></tr></thead>
            <tbody>
              {s.lines.map((l) => (
                <tr key={l.id}>
                  <td>
                    {l.name}
                    {l.modifiers.length > 0 && <div className="text-xs text-slate-500">+ {l.modifiers.map((m) => m.name).join(', ')}</div>}
                    {toNumber(l.refunded_quantity) > 0 && <div className="text-xs text-amber-600">{qty(l.refunded_quantity)} refunded</div>}
                  </td>
                  <td className="text-right">{qty(l.quantity)}</td>
                  <td className="text-right">{money(l.unit_price)}</td>
                  <td className="text-right">{toNumber(l.discount) ? money(l.discount) : ''}</td>
                  <td className="text-right font-semibold">{money(l.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1 text-sm">
              <div className="label">Payments</div>
              {s.payments.map((p) => (
                <div key={p.id} className="flex justify-between">
                  <span>{p.method_label}{p.momo_network && ` (${p.momo_network.toUpperCase()})`}{p.reference && ` · ${p.reference}`}</span>
                  <span>{money(p.amount)}</span>
                </div>
              ))}
              {toNumber(s.change_due) > 0 && <div className="flex justify-between text-slate-500"><span>Change given</span><span>{money(s.change_due)}</span></div>}
            </div>
            <div className="space-y-1 text-sm">
              <div className="flex justify-between"><span>Subtotal</span><span>{money(s.subtotal)}</span></div>
              {toNumber(s.discount_total) > 0 && <div className="flex justify-between"><span>Discount{s.approved_by_name && ` (approved by ${s.approved_by_name})`}</span><span>−{money(s.discount_total)}</span></div>}
              {s.taxes.map((t) => <div key={t.code} className="flex justify-between text-slate-500"><span>{t.name}</span><span>{money(t.amount)}</span></div>)}
              <div className="flex justify-between text-lg font-bold"><span>Total</span><span>{money(s.total)}</span></div>
            </div>
          </div>
          {s.refunds.length > 0 && (
            <div>
              <div className="label">Refunds</div>
              {s.refunds.map((r) => (
                <div key={r.id} className="mb-1 flex items-center justify-between rounded bg-amber-50 px-3 py-2 text-sm">
                  <span>{r.number} · {dateTime(r.created_at)} · {METHOD_LABELS[r.method]} · {r.reason}</span>
                  <span className="flex items-center gap-2 font-semibold">
                    {money(r.amount)}
                    <button className="text-xs text-brand-700" onClick={() => settings && printDoc(<RefundDoc refund={r} settings={settings} />, settings.receipt_width)}>Print</button>
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {refunding && s && (
        <RefundModal
          sale={s}
          onClose={() => setRefunding(false)}
          onDone={(r) => {
            setRefunding(false)
            qc.invalidateQueries({ queryKey: ['sale', id] })
            refresh()
            toast.success(`Refunded ${money(r.amount)}`)
            if (settings && window.confirm('Print refund slip?')) printDoc(<RefundDoc refund={r} settings={settings} />, settings.receipt_width)
          }}
        />
      )}
    </Modal>
  )
}

function Info({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div>{value}</div>
    </div>
  )
}

function RefundModal({ sale, onClose, onDone }: { sale: Sale; onClose: () => void; onDone: (r: Refund) => void }) {
  const [quantities, setQuantities] = useState<Record<number, number>>({})
  const firstMethod = sale.payments.find((p) => p.method !== 'points')?.method ?? 'cash'
  const [method, setMethod] = useState<PaymentMethod>(firstMethod)
  const [reason, setReason] = useState('')
  const [reference, setReference] = useState('')
  const [restock, setRestock] = useState(true)
  const [busy, setBusy] = useState(false)

  const lines = sale.lines.map((l) => ({ ...l, remaining: toNumber(l.quantity) - toNumber(l.refunded_quantity) })).filter((l) => l.remaining > 0)
  const estimate = lines.reduce((s, l) => s + (toNumber(l.total) / toNumber(l.quantity)) * (quantities[l.id] ?? 0), 0)
  const selected = Object.entries(quantities).filter(([, q]) => q > 0)

  const submit = async () => {
    setBusy(true)
    try {
      const refund = await withApproval((pin) =>
        api.post<Refund>(`/sales/${sale.id}/refund/`, {
          lines: selected.map(([line, quantity]) => ({ line: Number(line), quantity: String(quantity) })),
          method, reason, restock, reference, approval_pin: pin,
        }),
      )
      onDone(refund)
    } catch (err) {
      if (!isCancelled(err)) toast.error(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open
      size="lg"
      onClose={onClose}
      title={`Refund ${sale.invoice_number}`}
      footer={
        <>
          <span className="mr-auto text-sm">About <b>{money(estimate)}</b> to refund</span>
          <Button variant="secondary" onClick={() => setQuantities(Object.fromEntries(lines.map((l) => [l.id, l.remaining])))}>Select all</Button>
          <Button loading={busy} disabled={!selected.length || !reason} onClick={submit}>Refund</Button>
        </>
      }
    >
      <table className="table mb-4">
        <thead><tr><th>Item</th><th className="text-right">Can refund</th><th className="w-40 text-right">Refund qty</th></tr></thead>
        <tbody>
          {lines.map((l) => (
            <tr key={l.id}>
              <td>{l.name}</td>
              <td className="text-right">{qty(l.remaining)}</td>
              <td className="text-right">
                <input
                  type="number"
                  min={0}
                  max={l.remaining}
                  step="any"
                  className="input w-28 text-right"
                  value={quantities[l.id] ?? 0}
                  onChange={(e) => setQuantities({ ...quantities, [l.id]: Math.min(Math.max(toNumber(e.target.value), 0), l.remaining) })}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Refund by">
          <select className="input" value={method} onChange={(e) => setMethod(e.target.value as PaymentMethod)}>
            {(['cash', 'momo', 'card', 'bank', ...(sale.customer ? ['credit'] : [])] as PaymentMethod[]).map((m) => (
              <option key={m} value={m}>{m === 'credit' ? 'Reduce customer balance' : METHOD_LABELS[m]}</option>
            ))}
          </select>
        </Field>
        <Field label="Reference (MoMo / card)">
          <input className="input" value={reference} onChange={(e) => setReference(e.target.value)} />
        </Field>
        <Field label="Reason" className="sm:col-span-2">
          <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Damaged, wrong size" />
        </Field>
      </div>
      <Toggle checked={restock} onChange={setRestock} label="Put items back in stock" hint="Turn off for damaged or expired goods." />
    </Modal>
  )
}
