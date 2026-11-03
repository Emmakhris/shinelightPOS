import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { ApiError, api } from '../../api/client'
import type { PaymentInput, PosItem, Quote, Sale } from '../../api/types'
import { isCancelled, withApproval } from '../../components/approval'
import { toast } from '../../components/toast'
import { Button } from '../../components/ui'
import { money, qty, toNumber } from '../../lib/format'
import { useCurrentShift, usePosItems, useRefreshAfterSale, useSettings } from '../../lib/hooks'
import { cartTotal, lineTotal, toApiLines, unitPrice, useCart, type CartLine } from '../../stores/cart'
import { OpenShiftModal } from '../shifts/OpenShiftModal'
import { ModifierModal } from './ModifierModal'
import { PaymentModal } from './PaymentModal'
import { ProductGrid } from './ProductGrid'
import { CartDiscountModal, CustomerPicker, HeldSalesModal, LineEditModal, SaleCompleteModal } from './parts'

type Dialog = 'customer' | 'discount' | 'pay' | 'held' | 'shift' | null

export function RegisterPage() {
  const cart = useCart()
  const settings = useSettings().data
  const shift = useCurrentShift()
  const items = usePosItems().data
  const refresh = useRefreshAfterSale()
  const scanRef = useRef<HTMLInputElement>(null)
  const [search, setSearch] = useState('')
  const [dialog, setDialog] = useState<Dialog>(null)
  const [modifierItem, setModifierItem] = useState<PosItem | null>(null)
  const [editing, setEditing] = useState<CartLine | null>(null)
  const [completed, setCompleted] = useState<Sale | null>(null)
  const [busy, setBusy] = useState(false)

  const quoteBody = {
    lines: toApiLines(cart.lines),
    discount_type: cart.discountType,
    discount_value: String(cart.discountValue || 0),
  }
  const quote = useQuery({
    queryKey: ['quote', quoteBody],
    queryFn: () => api.post<Quote>('/sales/quote/', quoteBody),
    enabled: cart.lines.length > 0,
    placeholderData: keepPreviousData,
    retry: false,
  })
  const total = cart.lines.length ? toNumber(quote.data?.total ?? cartTotal(cart)) : 0

  const focusScan = () => window.setTimeout(() => scanRef.current?.focus(), 0)
  useEffect(() => {
    focusScan()
  }, [])

  const needsShift = settings?.require_open_shift && !shift.isLoading && !shift.data

  const pick = (item: PosItem) => {
    if (item.modifier_groups.length) {
      setModifierItem(item)
      return
    }
    cart.add(item)
    setSearch('')
    focusScan()
  }

  /** Enter in the scan box: exact barcode/SKU match adds the item; otherwise keep it as a search. */
  const onScan = async () => {
    const code = search.trim()
    if (!code) return
    const local = items?.find((i) => i.barcodes.includes(code) || i.sku?.toLowerCase() === code.toLowerCase())
    if (local) return pick(local)
    try {
      const found = await api.get<PosItem>(`/catalog/lookup/?code=${encodeURIComponent(code)}`)
      pick(found)
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 404)) toast.error(err)
      // Not a code: leave the text as a product search.
    }
  }

  const hold = async () => {
    if (!cart.lines.length) return
    const label = window.prompt('Name for this held sale (optional)') ?? ''
    try {
      await api.post('/sales/held/', {
        label,
        customer: cart.customer?.id ?? null,
        cart: { lines: cart.lines, customer: cart.customer, discountType: cart.discountType, discountValue: cart.discountValue, note: cart.note },
      })
      cart.clear()
      toast.success('Sale held')
    } catch (err) {
      toast.error(err)
    }
  }

  const checkout = async (payments: PaymentInput[]) => {
    setBusy(true)
    try {
      const sale = await withApproval((pin) =>
        api.post<Sale>('/sales/checkout/', {
          ...quoteBody,
          payments,
          customer: cart.customer?.id ?? null,
          note: cart.note,
          approval_pin: pin,
        }),
      )
      setDialog(null)
      setCompleted(sale)
      cart.clear()
      refresh()
    } catch (err) {
      if (!isCancelled(err)) toast.error(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-full flex-col lg:flex-row">
      {/* Products */}
      <section className="flex min-h-0 flex-1 flex-col bg-slate-100">
        <div className="flex items-center gap-2 p-3">
          <input
            ref={scanRef}
            className="input py-3 text-base"
            placeholder="Scan barcode or search products…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') onScan()
              if (e.key === 'Escape') setSearch('')
            }}
          />
          {search && (
            <Button variant="secondary" onClick={() => { setSearch(''); focusScan() }}>
              Clear
            </Button>
          )}
        </div>
        <ProductGrid onPick={pick} search={search} />
      </section>

      {/* Cart */}
      <section className="flex max-h-[55vh] w-full flex-col border-l border-slate-200 bg-white lg:max-h-none lg:w-[400px]">
        <div className="flex items-center gap-2 border-b border-slate-200 p-3">
          <button onClick={() => setDialog('customer')} className="flex-1 truncate rounded-lg border border-dashed border-slate-300 px-3 py-2 text-left text-sm hover:bg-slate-50">
            {cart.customer ? (
              <>
                <span className="font-semibold">👤 {cart.customer.name}</span>
                <span className="ml-2 text-xs text-slate-500">{cart.customer.loyalty_points} pts</span>
              </>
            ) : (
              <span className="text-slate-500">+ Add customer</span>
            )}
          </button>
          <Button variant="ghost" size="sm" onClick={() => setDialog('held')}>Recall</Button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {cart.lines.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center p-6 text-center text-slate-400">
              <div className="text-5xl">🛒</div>
              <p className="mt-2 text-sm">Scan or tap products to start a sale.</p>
            </div>
          )}
          {cart.lines.map((line) => (
            <div key={line.key} className="flex items-stretch border-b border-slate-100">
              <button onClick={() => setEditing(line)} className="min-w-0 flex-1 px-3 py-2 text-left hover:bg-slate-50">
                <div className="truncate text-sm font-semibold">{line.item.name}</div>
                {line.modifiers.length > 0 && <div className="truncate text-xs text-slate-500">+ {line.modifiers.map((m) => m.name).join(', ')}</div>}
                <div className="text-xs text-slate-500">
                  {qty(line.quantity)} × {money(unitPrice(line))}
                  {line.unitPrice !== undefined && <span className="ml-1 text-amber-600">(price changed)</span>}
                  {line.discountValue > 0 && <span className="ml-1 text-emerald-600">−{line.discountType === 'percent' ? `${line.discountValue}%` : money(line.discountValue)}</span>}
                </div>
                {line.note && <div className="truncate text-xs italic text-slate-400">{line.note}</div>}
              </button>
              <div className="flex flex-col items-end justify-center gap-1 px-2">
                <span className="text-sm font-bold">{money(lineTotal(line))}</span>
                <span className="flex gap-1">
                  <button className="h-7 w-7 rounded bg-slate-100 font-bold hover:bg-slate-200" onClick={() => line.quantity <= 1 ? cart.remove(line.key) : cart.update(line.key, { quantity: line.quantity - 1 })}>−</button>
                  <button className="h-7 w-7 rounded bg-slate-100 font-bold hover:bg-slate-200" onClick={() => cart.update(line.key, { quantity: line.quantity + 1 })}>+</button>
                </span>
              </div>
            </div>
          ))}
        </div>

        <div className="border-t border-slate-200 p-3">
          {quote.isError && <p className="mb-2 rounded bg-red-50 p-2 text-xs text-red-700">{(quote.error as Error).message}</p>}
          <div className="space-y-0.5 text-sm">
            <Row label="Subtotal" value={money(quote.data?.subtotal ?? 0)} />
            {toNumber(quote.data?.discount_total) > 0 && <Row label="Discount" value={`− ${money(quote.data?.discount_total)}`} className="text-emerald-700" />}
            <Row label={settings?.prices_include_tax ? 'Tax (included)' : 'Tax'} value={money(quote.data?.tax_total ?? 0)} className="text-slate-500" />
          </div>
          <div className="mt-1 flex items-baseline justify-between">
            <span className="text-lg font-bold">Total</span>
            <span className="text-3xl font-black">{money(total)}</span>
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2">
            <Button variant="secondary" disabled={!cart.lines.length} onClick={() => setDialog('discount')}>Discount</Button>
            <Button variant="secondary" disabled={!cart.lines.length} onClick={hold}>Hold</Button>
            <Button variant="secondary" disabled={!cart.lines.length} onClick={() => window.confirm('Clear this sale?') && cart.clear()}>Clear</Button>
          </div>
          {needsShift ? (
            <Button variant="primary" size="xl" className="mt-2 w-full" onClick={() => setDialog('shift')}>
              Open shift to start selling
            </Button>
          ) : (
            <Button
              variant="success"
              size="xl"
              className="mt-2 w-full"
              disabled={!cart.lines.length || quote.isFetching || quote.isError}
              onClick={() => setDialog('pay')}
            >
              Pay {cart.lines.length > 0 && money(total)}
            </Button>
          )}
        </div>
      </section>

      {dialog === 'customer' && <CustomerPicker onClose={() => setDialog(null)} onPick={(c) => { cart.setCustomer(c); setDialog(null) }} />}
      {dialog === 'discount' && (
        <CartDiscountModal type={cart.discountType} value={cart.discountValue} onClose={() => setDialog(null)} onSave={(t, v) => { cart.setDiscount(t, v); setDialog(null) }} />
      )}
      {dialog === 'held' && <HeldSalesModal onClose={() => setDialog(null)} onRecall={(snap) => { cart.load(snap); setDialog(null) }} />}
      {dialog === 'shift' && <OpenShiftModal onClose={() => setDialog(null)} />}
      {dialog === 'pay' && <PaymentModal total={total} customer={cart.customer} busy={busy} onClose={() => setDialog(null)} onComplete={checkout} />}
      {modifierItem && (
        <ModifierModal
          item={modifierItem}
          onClose={() => setModifierItem(null)}
          onConfirm={(mods, q, note) => {
            cart.add(modifierItem, mods, q)
            if (note) {
              const key = `${modifierItem.id}:${mods.map((m) => m.id).sort((a, b) => a - b).join(',')}`
              cart.update(key, { note })
            }
            setModifierItem(null)
            setSearch('')
            focusScan()
          }}
        />
      )}
      {editing && (
        <LineEditModal
          line={editing}
          onClose={() => setEditing(null)}
          onRemove={() => { cart.remove(editing.key); setEditing(null) }}
          onSave={(patch) => { cart.update(editing.key, patch); setEditing(null) }}
        />
      )}
      {completed && <SaleCompleteModal sale={completed} onClose={() => { setCompleted(null); focusScan() }} />}
    </div>
  )
}

function Row({ label, value, className = '' }: { label: string; value: string; className?: string }) {
  return (
    <div className={`flex justify-between ${className}`}>
      <span>{label}</span>
      <span>{value}</span>
    </div>
  )
}
