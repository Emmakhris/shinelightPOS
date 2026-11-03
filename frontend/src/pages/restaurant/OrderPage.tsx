import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../../api/client'
import type { Customer, FloorAreaWithTables, KitchenTicket, Order, OrderItem, PaymentInput, PosItem, Quote, Sale } from '../../api/types'
import { isCancelled, withApproval } from '../../components/approval'
import { BillDoc, KitchenTicketDoc, printDoc } from '../../components/print'
import { toast } from '../../components/toast'
import { Badge, Button, Loading, Modal } from '../../components/ui'
import { ORDER_TYPE_LABELS, money, qty, time, toNumber } from '../../lib/format'
import { useCurrentShift, useRefreshAfterSale, useSettings } from '../../lib/hooks'
import type { DiscountType } from '../../stores/cart'
import { ModifierModal } from '../pos/ModifierModal'
import { PaymentModal } from '../pos/PaymentModal'
import { ProductGrid } from '../pos/ProductGrid'
import { CartDiscountModal, CustomerPicker, SaleCompleteModal } from '../pos/parts'
import { OpenShiftModal } from '../shifts/OpenShiftModal'

type Dialog = 'pay' | 'discount' | 'customer' | 'move' | 'merge' | 'shift' | null

export function OrderPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const settings = useSettings().data
  const shift = useCurrentShift()
  const refresh = useRefreshAfterSale()
  const [search, setSearch] = useState('')
  const [modifierItem, setModifierItem] = useState<PosItem | null>(null)
  const [dialog, setDialog] = useState<Dialog>(null)
  const [discount, setDiscount] = useState<{ type: DiscountType; value: number }>({ type: 'amount', value: 0 })
  const [customer, setCustomer] = useState<Customer | null>(null)
  const [completed, setCompleted] = useState<Sale | null>(null)
  const [busy, setBusy] = useState(false)

  const order = useQuery({ queryKey: ['order', id], queryFn: () => api.get<Order>(`/restaurant/orders/${id}/`) })
  const liveItems = order.data?.items.filter((i) => i.status !== 'cancelled') ?? []
  const bill = useQuery({
    queryKey: ['bill', id, discount, order.data?.items.map((i) => `${i.id}:${i.quantity}:${i.status}`).join('|')],
    queryFn: () => api.post<Quote>(`/restaurant/orders/${id}/bill/`, { discount_type: discount.type, discount_value: discount.value }),
    enabled: liveItems.length > 0 && order.data?.status === 'open',
    retry: false,
  })

  const setOrder = (o: Order) => {
    qc.setQueryData(['order', id], o)
    qc.invalidateQueries({ queryKey: ['floor'] })
  }

  const run = async (fn: () => Promise<void>) => {
    try {
      await fn()
    } catch (err) {
      if (!isCancelled(err)) toast.error(err)
    }
  }

  const addItem = (item: PosItem, modifiers: number[] = [], quantity = 1, note = '') =>
    run(async () => setOrder(await api.post<Order>(`/restaurant/orders/${id}/items/`, { variant: item.id, quantity, modifiers, note })))

  const pick = (item: PosItem) => (item.modifier_groups.length ? setModifierItem(item) : addItem(item))

  const changeQty = (item: OrderItem, delta: number) =>
    run(async () => setOrder(await api.patch<Order>(`/restaurant/orders/${id}/items/${item.id}/`, { quantity: toNumber(item.quantity) + delta })))

  const removeItem = (item: OrderItem) =>
    run(async () => {
      if (item.status === 'sent' && !window.confirm(`${item.name} was already sent to the kitchen. Remove it?`)) return
      setOrder(await withApproval((pin) => api.del<Order>(`/restaurant/orders/${id}/items/${item.id}/`, { approval_pin: pin })))
    })

  const send = () =>
    run(async () => {
      const res = await api.post<{ ticket: KitchenTicket | null; order: Order }>(`/restaurant/orders/${id}/send/`)
      setOrder(res.order)
      if (res.ticket) printDoc(<KitchenTicketDoc ticket={res.ticket} />, settings?.receipt_width)
      toast.success(res.ticket ? 'Sent to kitchen' : 'Items marked as served')
    })

  const printBill = () => {
    if (bill.data && order.data && settings) printDoc(<BillDoc order={order.data} quote={bill.data} settings={settings} />, settings.receipt_width)
  }

  const pay = async (payments: PaymentInput[]) => {
    setBusy(true)
    try {
      const sale = await withApproval((pin) =>
        api.post<Sale>(`/restaurant/orders/${id}/pay/`, {
          payments,
          discount_type: discount.type,
          discount_value: String(discount.value),
          customer: customer?.id ?? null,
          approval_pin: pin,
        }),
      )
      setDialog(null)
      setCompleted(sale)
      refresh()
      qc.invalidateQueries({ queryKey: ['floor'] })
    } catch (err) {
      if (!isCancelled(err)) toast.error(err)
    } finally {
      setBusy(false)
    }
  }

  const cancelOrder = () =>
    run(async () => {
      if (!window.confirm('Cancel this whole order?')) return
      const reason = window.prompt('Reason for cancelling') ?? ''
      await withApproval((pin) => api.post(`/restaurant/orders/${id}/cancel/`, { reason, approval_pin: pin }))
      qc.invalidateQueries({ queryKey: ['floor'] })
      navigate('/tables')
    })

  if (order.isLoading) return <Loading />
  const o = order.data
  if (!o) return null
  if (o.status !== 'open' && !completed) {
    return (
      <div className="p-6">
        <p className="mb-3">This order is {o.status}.</p>
        <Button onClick={() => navigate('/tables')}>Back to tables</Button>
      </div>
    )
  }
  const pending = liveItems.filter((i) => i.status === 'pending').length
  const needsShift = settings?.require_open_shift && !shift.isLoading && !shift.data
  const total = toNumber(bill.data?.total ?? o.estimated_total)

  return (
    <div className="flex h-full flex-col lg:flex-row">
      <section className="flex min-h-0 flex-1 flex-col bg-slate-100">
        <div className="flex items-center gap-2 p-3">
          <Button variant="secondary" onClick={() => navigate('/tables')}>← Tables</Button>
          <input className="input py-3" placeholder="Search menu…" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <ProductGrid onPick={pick} search={search} />
      </section>

      <section className="flex max-h-[60vh] w-full flex-col border-l border-slate-200 bg-white lg:max-h-none lg:w-[420px]">
        <div className="border-b border-slate-200 p-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xl font-black">{o.table_name ? `Table ${o.table_name}` : ORDER_TYPE_LABELS[o.order_type]}</div>
              <div className="text-xs text-slate-500">
                Order #{o.number} · {o.guests} guests · {o.waiter_name} · {time(o.created_at)}
                {o.customer_label && ` · ${o.customer_label}`}
              </div>
            </div>
            <div className="flex gap-1">
              {o.table && <Button size="sm" variant="ghost" onClick={() => setDialog('move')}>Move</Button>}
              <Button size="sm" variant="ghost" onClick={() => setDialog('merge')}>Merge</Button>
            </div>
          </div>
          <button onClick={() => setDialog('customer')} className="mt-2 w-full rounded-lg border border-dashed border-slate-300 px-3 py-1.5 text-left text-sm text-slate-600 hover:bg-slate-50">
            {customer ? `👤 ${customer.name}` : '+ Customer (for loyalty points)'}
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {o.items.map((i) => (
            <div key={i.id} className={`flex items-center gap-2 border-b border-slate-100 px-3 py-2 ${i.status === 'cancelled' ? 'opacity-40' : ''}`}>
              <div className="min-w-0 flex-1">
                <div className={`truncate text-sm font-semibold ${i.status === 'cancelled' ? 'line-through' : ''}`}>
                  {qty(i.quantity)} × {i.name}
                </div>
                {i.modifier_details.length > 0 && <div className="truncate text-xs text-slate-500">+ {i.modifier_details.map((m) => m.name).join(', ')}</div>}
                {i.note && <div className="text-xs italic text-slate-400">{i.note}</div>}
                <div className="mt-0.5">
                  {i.status === 'pending' ? <Badge color="amber">Not sent</Badge> : i.status === 'sent' ? <Badge color="green">Sent</Badge> : <Badge color="red">Cancelled</Badge>}
                </div>
              </div>
              <span className="text-sm font-bold">{money(toNumber(i.unit_price) * toNumber(i.quantity))}</span>
              {i.status === 'pending' && (
                <span className="flex gap-1">
                  <button className="h-7 w-7 rounded bg-slate-100 font-bold" onClick={() => changeQty(i, -1)}>−</button>
                  <button className="h-7 w-7 rounded bg-slate-100 font-bold" onClick={() => changeQty(i, 1)}>+</button>
                </span>
              )}
              {i.status !== 'cancelled' && (
                <button className="px-1 text-red-500" title="Remove" onClick={() => removeItem(i)}>✕</button>
              )}
            </div>
          ))}
          {o.items.length === 0 && <p className="p-6 text-center text-sm text-slate-400">Tap menu items to add them to this order.</p>}
        </div>
        <div className="border-t border-slate-200 p-3">
          {bill.data && toNumber(bill.data.discount_total) > 0 && (
            <div className="flex justify-between text-sm text-emerald-700">
              <span>Discount</span>
              <span>− {money(bill.data.discount_total)}</span>
            </div>
          )}
          <div className="flex items-baseline justify-between">
            <span className="text-lg font-bold">Total</span>
            <span className="text-3xl font-black">{money(total)}</span>
          </div>
          <Button size="xl" className="mt-2 w-full" disabled={!pending} onClick={send}>
            Send to kitchen {pending > 0 && `(${pending})`}
          </Button>
          <div className="mt-2 grid grid-cols-3 gap-2">
            <Button variant="secondary" disabled={!liveItems.length} onClick={printBill}>Print bill</Button>
            <Button variant="secondary" disabled={!liveItems.length} onClick={() => setDialog('discount')}>Discount</Button>
            <Button variant="secondary" onClick={cancelOrder}>Cancel</Button>
          </div>
          {needsShift ? (
            <Button size="xl" className="mt-2 w-full" onClick={() => setDialog('shift')}>Open shift to take payment</Button>
          ) : (
            <Button variant="success" size="xl" className="mt-2 w-full" disabled={!liveItems.length || bill.isFetching || bill.isError} onClick={() => setDialog('pay')}>
              Pay {money(total)}
            </Button>
          )}
        </div>
      </section>

      {modifierItem && (
        <ModifierModal
          item={modifierItem}
          onClose={() => setModifierItem(null)}
          onConfirm={(mods, q, note) => {
            addItem(modifierItem, mods.map((m) => m.id), q, note)
            setModifierItem(null)
          }}
        />
      )}
      {dialog === 'pay' && <PaymentModal total={total} customer={customer} busy={busy} onClose={() => setDialog(null)} onComplete={pay} />}
      {dialog === 'discount' && (
        <CartDiscountModal type={discount.type} value={discount.value} onClose={() => setDialog(null)} onSave={(type, value) => { setDiscount({ type, value }); setDialog(null) }} />
      )}
      {dialog === 'customer' && <CustomerPicker onClose={() => setDialog(null)} onPick={(c) => { setCustomer(c); setDialog(null) }} />}
      {dialog === 'shift' && <OpenShiftModal onClose={() => setDialog(null)} />}
      {(dialog === 'move' || dialog === 'merge') && (
        <TablePicker
          mode={dialog}
          order={o}
          onClose={() => setDialog(null)}
          onDone={(updated) => { setOrder(updated); setDialog(null) }}
        />
      )}
      {completed && <SaleCompleteModal sale={completed} onClose={() => navigate('/tables')} />}
    </div>
  )
}

function TablePicker({ mode, order, onClose, onDone }: { mode: 'move' | 'merge'; order: Order; onClose: () => void; onDone: (o: Order) => void }) {
  const floor = useQuery({ queryKey: ['floor'], queryFn: () => api.get<FloorAreaWithTables[]>('/restaurant/floor/') })
  const choose = async (tableId: number, otherOrder: Order | null) => {
    try {
      if (mode === 'move') onDone(await api.post<Order>(`/restaurant/orders/${order.id}/move/`, { table: tableId }))
      else if (otherOrder) onDone(await api.post<Order>(`/restaurant/orders/${order.id}/merge/`, { order: otherOrder.id }))
    } catch (err) {
      toast.error(err)
    }
  }
  return (
    <Modal open onClose={onClose} title={mode === 'move' ? 'Move to which table?' : 'Merge which table into this order?'}>
      {floor.data?.map((a) => (
        <div key={a.id} className="mb-3">
          <div className="label">{a.name}</div>
          <div className="grid grid-cols-4 gap-2">
            {a.tables.filter((t) => t.id !== order.table).map((t) => {
              const usable = mode === 'move' ? !t.order : !!t.order && t.order.id !== order.id
              return (
                <Button key={t.id} variant="secondary" disabled={!usable} onClick={() => choose(t.id, t.order)}>
                  {t.name}
                </Button>
              )
            })}
          </div>
        </div>
      ))}
    </Modal>
  )
}
