import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api/client'
import type { Customer, HeldSale, Sale } from '../../api/types'
import { NumPad } from '../../components/NumPad'
import { ReceiptDoc, printDoc } from '../../components/print'
import { toast } from '../../components/toast'
import { Button, Empty, Field, Modal } from '../../components/ui'
import { dateTime, money, toNumber } from '../../lib/format'
import { useCustomers, useSettings } from '../../lib/hooks'
import { lineGross, unitPrice, type CartLine, type CartSnapshot, type DiscountType } from '../../stores/cart'

export function CustomerPicker({ onClose, onPick }: { onClose: () => void; onPick: (c: Customer | null) => void }) {
  const [search, setSearch] = useState('')
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ name: '', phone: '' })
  const customers = useCustomers(search)
  const qc = useQueryClient()
  const create = useMutation({
    mutationFn: () => api.post<Customer>('/customers/', form),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ['customers'] })
      onPick(c)
    },
    onError: (e) => toast.error(e),
  })

  return (
    <Modal open onClose={onClose} title="Customer">
      {creating ? (
        <div className="space-y-3">
          <Field label="Name">
            <input className="input" autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
          <Field label="Phone">
            <input className="input" inputMode="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </Field>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setCreating(false)}>Back</Button>
            <Button className="flex-1" disabled={!form.name} loading={create.isPending} onClick={() => create.mutate()}>
              Save & use
            </Button>
          </div>
        </div>
      ) : (
        <>
          <div className="mb-3 flex gap-2">
            <input className="input" autoFocus placeholder="Search name or phone" value={search} onChange={(e) => setSearch(e.target.value)} />
            <Button variant="secondary" onClick={() => { setCreating(true); setForm({ name: /\d/.test(search) ? '' : search, phone: /\d/.test(search) ? search : '' }) }}>
              + New
            </Button>
          </div>
          <div className="max-h-80 space-y-1 overflow-y-auto">
            {customers.data?.map((c) => (
              <button key={c.id} onClick={() => onPick(c)} className="flex w-full items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-left hover:bg-slate-50">
                <span>
                  <span className="font-semibold">{c.name}</span>
                  <span className="block text-xs text-slate-500">{c.phone}</span>
                </span>
                <span className="text-right text-xs text-slate-500">
                  {toNumber(c.loyalty_points) > 0 && <span className="block">{c.loyalty_points} pts</span>}
                  {toNumber(c.balance) > 0 && <span className="block text-red-600">owes {money(c.balance)}</span>}
                </span>
              </button>
            ))}
            {customers.data?.length === 0 && <Empty>No customers found.</Empty>}
          </div>
          <Button variant="ghost" className="mt-3 w-full" onClick={() => onPick(null)}>
            Walk-in customer (none)
          </Button>
        </>
      )}
    </Modal>
  )
}

export function LineEditModal({ line, onClose, onSave, onRemove }: {
  line: CartLine
  onClose: () => void
  onSave: (patch: Partial<CartLine>) => void
  onRemove: () => void
}) {
  const [quantity, setQuantity] = useState(String(line.quantity))
  const [discountType, setDiscountType] = useState<DiscountType>(line.discountType)
  const [discount, setDiscount] = useState(line.discountValue ? String(line.discountValue) : '')
  const [price, setPrice] = useState(line.unitPrice !== undefined ? String(line.unitPrice) : '')
  const [note, setNote] = useState(line.note)
  const [field, setField] = useState<'quantity' | 'discount' | 'price'>('quantity')
  const values = { quantity, discount, price }
  const setters = { quantity: setQuantity, discount: setDiscount, price: setPrice }

  const save = () => {
    const q = toNumber(quantity)
    if (q <= 0) return onRemove()
    if (!line.item.allows_fraction && !Number.isInteger(q)) {
      toast.error(`${line.item.name} is sold in whole units.`)
      return
    }
    onSave({
      quantity: q,
      discountType,
      discountValue: toNumber(discount),
      unitPrice: price === '' ? undefined : toNumber(price),
      note,
    })
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={line.item.name}
      footer={
        <>
          <Button variant="danger" className="mr-auto" onClick={onRemove}>Remove</Button>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={save}>Save</Button>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-3">
          <Field label={`Quantity (${line.item.unit})`}>
            <input className={`input text-lg ${field === 'quantity' ? 'ring-2 ring-brand-300' : ''}`} value={quantity} onFocus={() => setField('quantity')} onChange={(e) => setQuantity(e.target.value)} inputMode="decimal" />
          </Field>
          <Field label="Line discount">
            <div className="flex gap-2">
              <select className="input w-24" value={discountType} onChange={(e) => setDiscountType(e.target.value as DiscountType)}>
                <option value="amount">GH₵</option>
                <option value="percent">%</option>
              </select>
              <input className={`input ${field === 'discount' ? 'ring-2 ring-brand-300' : ''}`} value={discount} onFocus={() => setField('discount')} onChange={(e) => setDiscount(e.target.value)} inputMode="decimal" placeholder="0" />
            </div>
          </Field>
          <Field label="Price each" hint={`List price ${money(unitPrice({ ...line, unitPrice: undefined }))}. Changing it needs a manager.`}>
            <input className={`input ${field === 'price' ? 'ring-2 ring-brand-300' : ''}`} value={price} onFocus={() => setField('price')} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" placeholder={unitPrice({ ...line, unitPrice: undefined }).toFixed(2)} />
          </Field>
          <Field label="Note">
            <input className="input" value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <p className="text-sm text-slate-500">Line value before discount: {money(lineGross(line))}</p>
        </div>
        <NumPad value={values[field]} onChange={setters[field]} allowDecimal={field !== 'quantity' || line.item.allows_fraction} />
      </div>
    </Modal>
  )
}

export function CartDiscountModal({ type, value, onClose, onSave }: {
  type: DiscountType
  value: number
  onClose: () => void
  onSave: (type: DiscountType, value: number) => void
}) {
  const [t, setT] = useState<DiscountType>(type)
  const [v, setV] = useState(value ? String(value) : '')
  return (
    <Modal open size="sm" onClose={onClose} title="Discount on whole sale">
      <div className="mb-3 grid grid-cols-2 gap-2">
        {(['percent', 'amount'] as const).map((opt) => (
          <Button key={opt} variant={t === opt ? 'primary' : 'secondary'} onClick={() => setT(opt)}>
            {opt === 'percent' ? 'Percent %' : 'Amount GH₵'}
          </Button>
        ))}
      </div>
      <div className="mb-2 flex h-12 items-center justify-end rounded-lg border px-3 text-2xl font-bold">{v || '0'}{t === 'percent' ? '%' : ''}</div>
      <NumPad value={v} onChange={setV} />
      <div className="mt-3 grid grid-cols-2 gap-2">
        <Button variant="secondary" onClick={() => onSave('amount', 0)}>Remove discount</Button>
        <Button onClick={() => onSave(t, toNumber(v))}>Apply</Button>
      </div>
    </Modal>
  )
}

export function SaleCompleteModal({ sale, onClose }: { sale: Sale; onClose: () => void }) {
  const settings = useSettings().data
  const print = () => settings && printDoc(<ReceiptDoc sale={sale} settings={settings} />, settings.receipt_width)
  return (
    <Modal open size="sm" onClose={onClose} title="Sale complete">
      <div className="text-center">
        <div className="text-sm text-slate-500">{sale.invoice_number}</div>
        <div className="my-2 text-4xl font-black text-emerald-600">{money(sale.total)}</div>
        {toNumber(sale.change_due) > 0 && (
          <div className="mb-3 rounded-xl bg-amber-50 p-4">
            <div className="text-xs font-semibold uppercase text-amber-700">Give change</div>
            <div className="text-4xl font-black text-amber-700">{money(sale.change_due)}</div>
          </div>
        )}
        {toNumber(sale.points_earned) > 0 && <p className="mb-3 text-sm text-slate-600">{sale.customer_name} earned {sale.points_earned} points.</p>}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Button variant="secondary" size="lg" onClick={print}>🖨 Print receipt</Button>
        <Button size="lg" autoFocus onClick={onClose}>New sale</Button>
      </div>
    </Modal>
  )
}

export function HeldSalesModal({ onClose, onRecall }: { onClose: () => void; onRecall: (snapshot: CartSnapshot) => void }) {
  const qc = useQueryClient()
  const held = useQuery({ queryKey: ['held'], queryFn: () => api.get<HeldSale[]>('/sales/held/') })
  const recall = async (h: HeldSale) => {
    await api.del(`/sales/held/${h.id}/`)
    qc.invalidateQueries({ queryKey: ['held'] })
    onRecall(h.cart as CartSnapshot)
  }
  return (
    <Modal open onClose={onClose} title="Held sales">
      <div className="space-y-2">
        {held.data?.map((h) => {
          const snap = h.cart as CartSnapshot
          return (
            <button key={h.id} onClick={() => recall(h)} className="flex w-full items-center justify-between rounded-lg border border-slate-200 p-3 text-left hover:bg-slate-50">
              <span>
                <span className="font-semibold">{h.label || `${snap.lines.length} items`}</span>
                <span className="block text-xs text-slate-500">
                  {h.user_name} · {dateTime(h.created_at)} {h.customer_name && `· ${h.customer_name}`}
                </span>
              </span>
              <span className="text-sm font-semibold text-brand-700">Recall</span>
            </button>
          )
        })}
        {held.data?.length === 0 && <Empty>No held sales.</Empty>}
      </div>
    </Modal>
  )
}
