import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api, downloadCsv, qs } from '../../api/client'
import type { Paginated, PurchaseOrder, PurchaseOrderLine, StockMovement, StockRow, Supplier } from '../../api/types'
import { toast } from '../../components/toast'
import { Badge, Button, Empty, Field, Loading, Modal, PageHeader, Tabs, Toggle } from '../../components/ui'
import { dateTime, money, qty, toNumber } from '../../lib/format'
import { usePosItems } from '../../lib/hooks'

type Tab = 'stock' | 'count' | 'movements' | 'orders' | 'suppliers'

export function InventoryPage() {
  const [tab, setTab] = useState<Tab>('stock')
  return (
    <div>
      <PageHeader title="Inventory" subtitle="Stock levels, counts, deliveries and suppliers." />
      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: 'stock', label: 'Stock levels' },
          { value: 'count', label: 'Stock count' },
          { value: 'movements', label: 'History' },
          { value: 'orders', label: 'Purchase orders' },
          { value: 'suppliers', label: 'Suppliers' },
        ]}
      />
      {tab === 'stock' && <StockLevels />}
      {tab === 'count' && <StockCount />}
      {tab === 'movements' && <Movements />}
      {tab === 'orders' && <PurchaseOrders />}
      {tab === 'suppliers' && <Suppliers />}
    </div>
  )
}

function useStock(search = '', low = false) {
  return useQuery({ queryKey: ['stock', search, low], queryFn: () => api.get<StockRow[]>(`/inventory/stock/${qs({ search, low: low ? 1 : undefined })}`) })
}

const ADJUST_REASONS = [
  ['damage', 'Damaged'], ['theft', 'Theft / loss'], ['expired', 'Expired'], ['internal_use', 'Internal use'],
  ['correction', 'Correction'], ['opening', 'Opening stock'],
]

function StockLevels() {
  const [search, setSearch] = useState('')
  const [low, setLow] = useState(false)
  const [adjusting, setAdjusting] = useState<StockRow | null>(null)
  const stock = useStock(search, low)
  const totals = useMemo(() => (stock.data ?? []).reduce((s, r) => s + toNumber(r.stock_value), 0), [stock.data])
  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <input className="input max-w-xs" placeholder="Search" value={search} onChange={(e) => setSearch(e.target.value)} />
        <Toggle checked={low} onChange={setLow} label="Only low stock" />
        <span className="ml-auto text-sm text-slate-600">Stock value at cost: <b>{money(totals)}</b></span>
        <Button variant="secondary" onClick={() => downloadCsv('/inventory/stock/', 'stock.csv').catch(toast.error)}>Export CSV</Button>
      </div>
      <div className="card overflow-x-auto">
        {stock.isLoading ? <Loading /> : (
          <table className="table">
            <thead><tr><th>Item</th><th>SKU</th><th>Category</th><th className="text-right">In stock</th><th className="text-right">Alert at</th><th className="text-right">Cost</th><th className="text-right">Value</th><th></th></tr></thead>
            <tbody>
              {stock.data?.map((r) => (
                <tr key={r.variant}>
                  <td className="font-semibold">{r.name}</td>
                  <td className="font-mono text-xs">{r.sku}</td>
                  <td>{r.category}</td>
                  <td className={`text-right font-semibold ${r.is_low ? 'text-red-600' : ''}`}>{qty(r.quantity)} {r.unit}</td>
                  <td className="text-right text-slate-500">{qty(r.low_stock_threshold)}</td>
                  <td className="text-right">{money(r.cost_price)}</td>
                  <td className="text-right">{money(r.stock_value)}</td>
                  <td className="text-right"><Button size="sm" variant="secondary" onClick={() => setAdjusting(r)}>Adjust</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {stock.data?.length === 0 && <Empty>{low ? 'Nothing is low on stock. 🎉' : 'No stock-tracked products.'}</Empty>}
      </div>
      {adjusting && <AdjustModal row={adjusting} onClose={() => setAdjusting(null)} />}
    </>
  )
}

function AdjustModal({ row, onClose }: { row: StockRow; onClose: () => void }) {
  const qc = useQueryClient()
  const [direction, setDirection] = useState<'remove' | 'add'>('remove')
  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('damage')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true)
    try {
      const change = toNumber(amount) * (direction === 'remove' ? -1 : 1)
      await api.post('/inventory/adjust/', { variant: row.variant, change: String(change), reason, note })
      qc.invalidateQueries({ queryKey: ['stock'] })
      qc.invalidateQueries({ queryKey: ['pos-items'] })
      toast.success('Stock updated')
      onClose()
    } catch (err) {
      toast.error(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open size="sm" onClose={onClose} title={`Adjust ${row.name}`} footer={<Button loading={busy} disabled={!toNumber(amount)} onClick={save}>Save</Button>}>
      <p className="mb-3 text-sm text-slate-600">Currently {qty(row.quantity)} {row.unit} in stock.</p>
      <div className="mb-3 grid grid-cols-2 gap-2">
        <Button variant={direction === 'remove' ? 'danger' : 'secondary'} onClick={() => setDirection('remove')}>− Remove</Button>
        <Button variant={direction === 'add' ? 'success' : 'secondary'} onClick={() => setDirection('add')}>+ Add</Button>
      </div>
      <div className="space-y-3">
        <Field label="Quantity"><input className="input" type="number" min={0} step="any" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
        <Field label="Reason">
          <select className="input" value={reason} onChange={(e) => setReason(e.target.value)}>
            {ADJUST_REASONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Field>
        <Field label="Note"><input className="input" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      </div>
    </Modal>
  )
}

function StockCount() {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const stock = useStock()
  const [counts, setCounts] = useState<Record<number, string>>({})
  const [busy, setBusy] = useState(false)
  const rows = (stock.data ?? []).filter((r) => !search || r.name.toLowerCase().includes(search.toLowerCase()) || r.sku.includes(search))
  const entered = Object.entries(counts).filter(([, v]) => v !== '')

  const submit = async () => {
    if (!window.confirm(`Save counts for ${entered.length} items? Differences are recorded as stock count adjustments.`)) return
    setBusy(true)
    try {
      const res = await api.post<{ changed: StockMovement[] }>('/inventory/count/', {
        lines: entered.map(([variant, counted]) => ({ variant: Number(variant), counted })),
      })
      toast.success(`${res.changed.length} items adjusted`)
      setCounts({})
      qc.invalidateQueries({ queryKey: ['stock'] })
      qc.invalidateQueries({ queryKey: ['pos-items'] })
    } catch (err) {
      toast.error(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <p className="mb-3 text-sm text-slate-600">Count what is on the shelf and type it in. Leave items blank to skip them. Only differences are saved.</p>
      <div className="mb-3 flex gap-2">
        <input className="input max-w-xs" placeholder="Search" value={search} onChange={(e) => setSearch(e.target.value)} />
        <Button className="ml-auto" disabled={!entered.length} loading={busy} onClick={submit}>Save count ({entered.length})</Button>
      </div>
      <div className="card overflow-x-auto">
        <table className="table">
          <thead><tr><th>Item</th><th className="text-right">System qty</th><th className="w-40 text-right">Counted</th><th className="text-right">Difference</th></tr></thead>
          <tbody>
            {rows.map((r) => {
              const c = counts[r.variant]
              const diff = c !== undefined && c !== '' ? toNumber(c) - toNumber(r.quantity) : null
              return (
                <tr key={r.variant}>
                  <td>{r.name}</td>
                  <td className="text-right">{qty(r.quantity)}</td>
                  <td className="text-right">
                    <input className="input w-28 text-right" type="number" min={0} step="any" value={c ?? ''} onChange={(e) => setCounts({ ...counts, [r.variant]: e.target.value })} />
                  </td>
                  <td className={`text-right font-semibold ${diff === null ? '' : diff < 0 ? 'text-red-600' : diff > 0 ? 'text-emerald-600' : 'text-slate-400'}`}>
                    {diff === null ? '' : diff > 0 ? `+${qty(diff)}` : qty(diff)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}

function Movements() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [reason, setReason] = useState('')
  const data = useQuery({
    queryKey: ['movements', page, search, reason],
    queryFn: () => api.get<Paginated<StockMovement>>(`/inventory/movements/${qs({ page, search, reason })}`),
    placeholderData: keepPreviousData,
  })
  return (
    <>
      <div className="mb-3 flex gap-2">
        <input className="input max-w-xs" placeholder="Search product or reference" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
        <select className="input max-w-[200px]" value={reason} onChange={(e) => { setReason(e.target.value); setPage(1) }}>
          <option value="">All reasons</option>
          {[['sale', 'Sale'], ['refund', 'Refund'], ['void', 'Void'], ['purchase', 'Goods received'], ['count', 'Stock count'], ...ADJUST_REASONS].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>
      <div className="card overflow-x-auto">
        <table className="table">
          <thead><tr><th>When</th><th>Item</th><th>Reason</th><th className="text-right">Change</th><th className="text-right">After</th><th>Reference</th><th>By</th></tr></thead>
          <tbody>
            {data.data?.results.map((m) => (
              <tr key={m.id}>
                <td className="whitespace-nowrap">{dateTime(m.created_at)}</td>
                <td>{m.variant_name}</td>
                <td>{m.reason_label}{m.note && <div className="text-xs text-slate-500">{m.note}</div>}</td>
                <td className={`text-right font-semibold ${toNumber(m.change) < 0 ? 'text-red-600' : 'text-emerald-600'}`}>{toNumber(m.change) > 0 ? '+' : ''}{qty(m.change)}</td>
                <td className="text-right">{qty(m.quantity_after)}</td>
                <td className="font-mono text-xs">{m.reference}</td>
                <td>{m.user_name}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.data?.count === 0 && <Empty>No stock movements.</Empty>}
      </div>
      {data.data && data.data.count > 50 && (
        <div className="mt-3 flex justify-end gap-2">
          <Button size="sm" variant="secondary" disabled={!data.data.previous} onClick={() => setPage(page - 1)}>Previous</Button>
          <Button size="sm" variant="secondary" disabled={!data.data.next} onClick={() => setPage(page + 1)}>Next</Button>
        </div>
      )}
    </>
  )
}

const PO_COLORS = { draft: 'gray', ordered: 'blue', partial: 'amber', received: 'green', cancelled: 'red' } as const

function useSuppliers() {
  return useQuery({ queryKey: ['suppliers'], queryFn: () => api.get<Supplier[]>('/inventory/suppliers/') })
}

function PurchaseOrders() {
  const qc = useQueryClient()
  const orders = useQuery({ queryKey: ['purchase-orders'], queryFn: () => api.get<PurchaseOrder[]>('/inventory/purchase-orders/') })
  const [editing, setEditing] = useState<PurchaseOrder | 'new' | null>(null)
  const [receiving, setReceiving] = useState<PurchaseOrder | null>(null)
  const act = async (po: PurchaseOrder, action: 'mark_ordered' | 'cancel') => {
    try {
      await api.post(`/inventory/purchase-orders/${po.id}/${action}/`)
      qc.invalidateQueries({ queryKey: ['purchase-orders'] })
    } catch (err) {
      toast.error(err)
    }
  }
  return (
    <>
      <div className="mb-3 flex justify-end"><Button onClick={() => setEditing('new')}>+ New purchase order</Button></div>
      <div className="card overflow-x-auto">
        <table className="table">
          <thead><tr><th>Number</th><th>Supplier</th><th>Created</th><th>Items</th><th className="text-right">Total</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {orders.data?.map((po) => (
              <tr key={po.id}>
                <td className="font-mono text-xs font-semibold">{po.number}</td>
                <td>{po.supplier_name}</td>
                <td>{dateTime(po.created_at)}</td>
                <td>{po.lines.length}</td>
                <td className="text-right">{money(po.total)}</td>
                <td><Badge color={PO_COLORS[po.status]}>{po.status}</Badge></td>
                <td className="space-x-1 whitespace-nowrap text-right">
                  {(po.status === 'draft' || po.status === 'ordered') && <Button size="sm" variant="ghost" onClick={() => setEditing(po)}>Edit</Button>}
                  {po.status === 'draft' && <Button size="sm" variant="secondary" onClick={() => act(po, 'mark_ordered')}>Mark ordered</Button>}
                  {['draft', 'ordered', 'partial'].includes(po.status) && <Button size="sm" onClick={() => setReceiving(po)}>Receive</Button>}
                  {(po.status === 'draft' || po.status === 'ordered') && <Button size="sm" variant="ghost" onClick={() => window.confirm('Cancel this order?') && act(po, 'cancel')}>Cancel</Button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {orders.data?.length === 0 && <Empty>No purchase orders yet.</Empty>}
      </div>
      {editing && <PurchaseOrderForm order={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
      {receiving && <ReceiveModal order={receiving} onClose={() => setReceiving(null)} />}
    </>
  )
}

function PurchaseOrderForm({ order, onClose }: { order: PurchaseOrder | null; onClose: () => void }) {
  const qc = useQueryClient()
  const suppliers = useSuppliers()
  const items = usePosItems().data?.filter((i) => i.track_stock) ?? []
  const [supplier, setSupplier] = useState<number | ''>(order?.supplier ?? '')
  const [lines, setLines] = useState<PurchaseOrderLine[]>(order?.lines ?? [])
  const [notes, setNotes] = useState(order?.notes ?? '')
  const [search, setSearch] = useState('')
  const [busy, setBusy] = useState(false)
  const matches = search ? items.filter((i) => i.name.toLowerCase().includes(search.toLowerCase()) || i.barcodes.includes(search)).slice(0, 8) : []
  const total = lines.reduce((s, l) => s + toNumber(l.quantity_ordered) * toNumber(l.unit_cost), 0)

  const save = async () => {
    setBusy(true)
    try {
      const body = { supplier, notes, lines: lines.map(({ variant, quantity_ordered, unit_cost }) => ({ variant, quantity_ordered, unit_cost })) }
      if (order) await api.put(`/inventory/purchase-orders/${order.id}/`, body)
      else await api.post('/inventory/purchase-orders/', body)
      qc.invalidateQueries({ queryKey: ['purchase-orders'] })
      onClose()
    } catch (err) {
      toast.error(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open size="lg" onClose={onClose} title={order ? `Edit ${order.number}` : 'New purchase order'}
      footer={<><span className="mr-auto font-semibold">Total {money(total)}</span><Button loading={busy} disabled={!supplier || !lines.length} onClick={save}>Save</Button></>}>
      <div className="mb-3 grid gap-3 sm:grid-cols-2">
        <Field label="Supplier">
          <select className="input" value={supplier} onChange={(e) => setSupplier(e.target.value ? Number(e.target.value) : '')}>
            <option value="">Choose…</option>
            {suppliers.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </Field>
        <Field label="Notes"><input className="input" value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
      </div>
      <div className="relative mb-3">
        <input className="input" placeholder="Search products to add…" value={search} onChange={(e) => setSearch(e.target.value)} />
        {matches.length > 0 && (
          <div className="absolute z-10 mt-1 w-full rounded-lg border bg-white shadow-lg">
            {matches.map((m) => (
              <button key={m.id} className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50" onClick={() => {
                if (!lines.some((l) => l.variant === m.id)) setLines([...lines, { variant: m.id, variant_name: m.name, quantity_ordered: '1', unit_cost: '' }])
                setSearch('')
              }}>
                {m.name} <span className="text-xs text-slate-500">· in stock {qty(m.stock)}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      <table className="table">
        <thead><tr><th>Item</th><th className="w-32">Qty</th><th className="w-32">Unit cost</th><th className="text-right">Line</th><th></th></tr></thead>
        <tbody>
          {lines.map((l, i) => (
            <tr key={l.variant}>
              <td>{l.variant_name}</td>
              <td><input className="input" type="number" min={0} step="any" value={l.quantity_ordered} onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, quantity_ordered: e.target.value } : x)))} /></td>
              <td><input className="input" inputMode="decimal" value={l.unit_cost} onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, unit_cost: e.target.value } : x)))} /></td>
              <td className="text-right">{money(toNumber(l.quantity_ordered) * toNumber(l.unit_cost))}</td>
              <td><Button size="sm" variant="ghost" onClick={() => setLines(lines.filter((_, j) => j !== i))}>✕</Button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </Modal>
  )
}

function ReceiveModal({ order, onClose }: { order: PurchaseOrder; onClose: () => void }) {
  const qc = useQueryClient()
  const [qtys, setQtys] = useState<Record<number, string>>(() =>
    Object.fromEntries(order.lines.map((l) => [l.id!, String(Math.max(toNumber(l.quantity_ordered) - toNumber(l.quantity_received), 0))])),
  )
  const [costs, setCosts] = useState<Record<number, string>>(() => Object.fromEntries(order.lines.map((l) => [l.id!, l.unit_cost])))
  const [invoice, setInvoice] = useState(order.supplier_invoice)
  const [updateCost, setUpdateCost] = useState(true)
  const [busy, setBusy] = useState(false)
  const receive = async () => {
    setBusy(true)
    try {
      await api.post(`/inventory/purchase-orders/${order.id}/receive/`, {
        supplier_invoice: invoice,
        update_cost: updateCost,
        lines: order.lines.map((l) => ({ line: l.id, quantity: qtys[l.id!] || '0', unit_cost: costs[l.id!] })),
      })
      qc.invalidateQueries({ queryKey: ['purchase-orders'] })
      qc.invalidateQueries({ queryKey: ['stock'] })
      qc.invalidateQueries({ queryKey: ['pos-items'] })
      toast.success('Goods received into stock')
      onClose()
    } catch (err) {
      toast.error(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open size="lg" onClose={onClose} title={`Receive ${order.number}`} footer={<Button loading={busy} onClick={receive}>Receive into stock</Button>}>
      <Field label="Supplier invoice number" className="mb-3"><input className="input" value={invoice} onChange={(e) => setInvoice(e.target.value)} /></Field>
      <table className="table mb-3">
        <thead><tr><th>Item</th><th className="text-right">Ordered</th><th className="text-right">Received</th><th className="w-28">Receiving now</th><th className="w-28">Unit cost</th></tr></thead>
        <tbody>
          {order.lines.map((l) => (
            <tr key={l.id}>
              <td>{l.variant_name}</td>
              <td className="text-right">{qty(l.quantity_ordered)}</td>
              <td className="text-right">{qty(l.quantity_received)}</td>
              <td><input className="input" type="number" min={0} step="any" value={qtys[l.id!]} onChange={(e) => setQtys({ ...qtys, [l.id!]: e.target.value })} /></td>
              <td><input className="input" inputMode="decimal" value={costs[l.id!]} onChange={(e) => setCosts({ ...costs, [l.id!]: e.target.value })} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <Toggle checked={updateCost} onChange={setUpdateCost} label="Update product cost prices" hint="Keeps profit reports accurate." />
    </Modal>
  )
}

function Suppliers() {
  const qc = useQueryClient()
  const suppliers = useSuppliers()
  const [edit, setEdit] = useState<Partial<Supplier> | null>(null)
  const save = async () => {
    if (!edit) return
    try {
      if (edit.id) await api.patch(`/inventory/suppliers/${edit.id}/`, edit)
      else await api.post('/inventory/suppliers/', edit)
      qc.invalidateQueries({ queryKey: ['suppliers'] })
      setEdit(null)
    } catch (err) {
      toast.error(err)
    }
  }
  return (
    <>
      <div className="mb-3 flex justify-end"><Button onClick={() => setEdit({ name: '', is_active: true })}>+ New supplier</Button></div>
      <div className="card overflow-x-auto">
        <table className="table">
          <thead><tr><th>Name</th><th>Contact</th><th>Phone</th><th>Email</th></tr></thead>
          <tbody>
            {suppliers.data?.map((s) => (
              <tr key={s.id} className="cursor-pointer" onClick={() => setEdit(s)}>
                <td className="font-semibold">{s.name}</td><td>{s.contact_name}</td><td>{s.phone}</td><td>{s.email}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {suppliers.data?.length === 0 && <Empty>No suppliers yet.</Empty>}
      </div>
      {edit && (
        <Modal open onClose={() => setEdit(null)} title={edit.id ? 'Edit supplier' : 'New supplier'} footer={<Button disabled={!edit.name} onClick={save}>Save</Button>}>
          <div className="grid gap-3 sm:grid-cols-2">
            {(['name', 'contact_name', 'phone', 'email'] as const).map((k) => (
              <Field key={k} label={k.replace('_', ' ')}><input className="input" value={edit[k] ?? ''} onChange={(e) => setEdit({ ...edit, [k]: e.target.value })} /></Field>
            ))}
            <Field label="Address" className="sm:col-span-2"><textarea className="input" rows={2} value={edit.address ?? ''} onChange={(e) => setEdit({ ...edit, address: e.target.value })} /></Field>
            <Field label="Notes" className="sm:col-span-2"><textarea className="input" rows={2} value={edit.notes ?? ''} onChange={(e) => setEdit({ ...edit, notes: e.target.value })} /></Field>
          </div>
        </Modal>
      )}
    </>
  )
}
