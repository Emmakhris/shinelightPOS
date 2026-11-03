import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import type { FloorAreaWithTables, Order, Table } from '../../api/types'
import { toast } from '../../components/toast'
import { Button, Empty, Field, Loading, Modal, PageHeader } from '../../components/ui'
import { ORDER_TYPE_LABELS, money, time } from '../../lib/format'

export function FloorPage() {
  const navigate = useNavigate()
  const floor = useQuery({
    queryKey: ['floor'],
    queryFn: () => api.get<FloorAreaWithTables[]>('/restaurant/floor/'),
    refetchInterval: 15_000,
  })
  const others = useQuery({
    queryKey: ['orders', 'open-other'],
    queryFn: () => api.get<Order[]>('/restaurant/orders/?status=open'),
    refetchInterval: 15_000,
    select: (orders) => orders.filter((o) => !o.table),
  })
  const [area, setArea] = useState<number | null>(null)
  const [newFor, setNewFor] = useState<{ table?: Table; type: Order['order_type'] } | null>(null)

  if (floor.isLoading) return <Loading />
  const areas = floor.data ?? []
  const current = areas.find((a) => a.id === area) ?? areas[0]

  return (
    <div>
      <PageHeader
        title="Tables"
        subtitle="Tap a free table to start an order, or an occupied one to add items or take payment."
        actions={
          <>
            <Button variant="secondary" onClick={() => setNewFor({ type: 'takeaway' })}>+ Takeaway</Button>
            <Button variant="secondary" onClick={() => setNewFor({ type: 'delivery' })}>+ Delivery</Button>
          </>
        }
      />
      {areas.length === 0 && <Empty>No tables yet. Add floor areas and tables in Settings → Tables.</Empty>}
      {areas.length > 1 && (
        <div className="mb-4 flex gap-2">
          {areas.map((a) => (
            <Button key={a.id} variant={current?.id === a.id ? 'primary' : 'secondary'} onClick={() => setArea(a.id)}>
              {a.name}
            </Button>
          ))}
        </div>
      )}
      {current && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6">
          {current.tables.map((t) => {
            const o = t.order
            return (
              <button
                key={t.id}
                onClick={() => (o ? navigate(`/tables/order/${o.id}`) : setNewFor({ table: t, type: 'dine_in' }))}
                className={`flex aspect-square flex-col rounded-2xl border-2 p-3 text-left shadow-sm transition active:scale-95 ${
                  o ? 'border-brand-400 bg-brand-50' : 'border-emerald-300 bg-white hover:bg-emerald-50'
                }`}
              >
                <span className="text-2xl font-black">{t.name}</span>
                <span className="text-xs text-slate-500">{t.seats} seats</span>
                {o ? (
                  <span className="mt-auto">
                    <span className="block text-lg font-bold text-brand-700">{money(o.estimated_total)}</span>
                    <span className="block text-xs text-slate-600">
                      {o.guests} guests · {time(o.created_at)} · {o.waiter_name}
                    </span>
                    {o.pending_count > 0 && <span className="mt-1 inline-block rounded bg-amber-200 px-1.5 text-xs font-semibold text-amber-900">{o.pending_count} not sent</span>}
                  </span>
                ) : (
                  <span className="mt-auto text-sm font-semibold text-emerald-600">Free</span>
                )}
              </button>
            )
          })}
        </div>
      )}

      <h2 className="mb-2 mt-8 text-lg font-bold">Takeaway & delivery</h2>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {others.data?.map((o) => (
          <button key={o.id} onClick={() => navigate(`/tables/order/${o.id}`)} className="card flex items-center justify-between p-3 text-left hover:border-brand-400">
            <span>
              <span className="font-semibold">#{o.number} · {ORDER_TYPE_LABELS[o.order_type]}</span>
              <span className="block text-xs text-slate-500">{o.customer_label || o.customer_name || 'No name'} · {time(o.created_at)}</span>
            </span>
            <span className="font-bold text-brand-700">{money(o.estimated_total)}</span>
          </button>
        ))}
        {others.data?.length === 0 && <p className="text-sm text-slate-500">No open takeaway or delivery orders.</p>}
      </div>

      {newFor && <NewOrderModal {...newFor} onClose={() => setNewFor(null)} onCreated={(o) => navigate(`/tables/order/${o.id}`)} />}
    </div>
  )
}

function NewOrderModal({ table, type, onClose, onCreated }: {
  table?: Table
  type: Order['order_type']
  onClose: () => void
  onCreated: (o: Order) => void
}) {
  const [guests, setGuests] = useState(2)
  const [label, setLabel] = useState('')
  const [busy, setBusy] = useState(false)
  const create = async () => {
    setBusy(true)
    try {
      onCreated(await api.post<Order>('/restaurant/orders/', { table: table?.id ?? null, order_type: type, guests, customer_label: label }))
    } catch (err) {
      toast.error(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open size="sm" onClose={onClose} title={table ? `New order · ${table.name}` : `New ${ORDER_TYPE_LABELS[type].toLowerCase()} order`}>
      {table ? (
        <>
          <span className="label">Guests</span>
          <div className="mb-4 grid grid-cols-6 gap-2">
            {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map((n) => (
              <Button key={n} variant={guests === n ? 'primary' : 'secondary'} onClick={() => setGuests(n)}>
                {n}
              </Button>
            ))}
          </div>
        </>
      ) : (
        <Field label="Customer name / phone" className="mb-4">
          <input className="input" autoFocus value={label} onChange={(e) => setLabel(e.target.value)} />
        </Field>
      )}
      <Button className="w-full" size="lg" loading={busy} onClick={create}>
        Start order
      </Button>
    </Modal>
  )
}
