import { useMemo, useState } from 'react'
import type { Customer, PaymentInput, PaymentMethod, PaystackCharge } from '../../api/types'
import { MomoPrompt } from './MomoPrompt'
import { NumPad } from '../../components/NumPad'
import { toast } from '../../components/toast'
import { Button, Modal } from '../../components/ui'
import { METHOD_LABELS, MOMO_NETWORKS, money, round2, toNumber } from '../../lib/format'
import { useSettings } from '../../lib/hooks'

const METHODS: PaymentMethod[] = ['cash', 'momo', 'card', 'bank', 'credit', 'points']

/** Collects one or more tenders. Calls onComplete with the payments once enough is tendered. */
export function PaymentModal({ total, customer, onClose, onComplete, busy }: {
  total: number
  customer: Customer | null
  onClose: () => void
  onComplete: (payments: PaymentInput[]) => void
  busy?: boolean
}) {
  const settings = useSettings().data
  const [payments, setPayments] = useState<PaymentInput[]>([])
  const [method, setMethod] = useState<PaymentMethod>('cash')
  const [amount, setAmount] = useState('')
  const [network, setNetwork] = useState('mtn')
  const [reference, setReference] = useState('')
  // With Paystack set up, MoMo goes out as a prompt to the customer's phone; cashiers can
  // still record a MoMo payment by hand (e.g. the customer paid to the merchant number).
  const [manualMomo, setManualMomo] = useState(false)
  const [prompting, setPrompting] = useState<number | null>(null)
  const paystackMode = settings?.paystack_mode ?? null
  const usePrompt = method === 'momo' && !!paystackMode && !manualMomo

  const paid = round2(payments.reduce((s, p) => s + toNumber(p.amount), 0))
  const remaining = round2(Math.max(total - paid, 0))
  const change = round2(Math.max(paid - total, 0))
  const pointValue = toNumber(settings?.loyalty_point_value)
  const pointsWorth = customer && pointValue ? round2(toNumber(customer.loyalty_points) * pointValue) : 0
  const creditAvailable = customer ? round2(toNumber(customer.credit_limit) - toNumber(customer.balance)) : 0

  const quickCash = useMemo(() => {
    const notes = [1, 2, 5, 10, 20, 50, 100, 200]
    const opts = new Set<number>([remaining])
    notes.forEach((n) => {
      const v = Math.ceil(remaining / n) * n
      if (v > remaining && v <= remaining + 200) opts.add(v)
    })
    return [...opts].sort((a, b) => a - b).slice(0, 5)
  }, [remaining])

  const methodDisabled = (m: PaymentMethod) => {
    if (m === 'credit') return !customer || creditAvailable <= 0
    if (m === 'points') return !customer || !settings?.loyalty_enabled || pointsWorth <= 0
    return false
  }

  const add = (value?: number) => {
    const amt = round2(value ?? (amount ? toNumber(amount) : remaining))
    if (amt <= 0) return
    if (method !== 'cash' && amt > remaining) {
      toast.error(`${METHOD_LABELS[method]} cannot be more than the ${money(remaining)} still due.`)
      return
    }
    if (usePrompt) {
      setPrompting(amt)
      return
    }
    setPayments((prev) => [
      ...prev,
      {
        method,
        amount: amt.toFixed(2),
        ...(method === 'momo' ? { momo_network: network } : {}),
        ...(reference ? { reference } : {}),
      },
    ])
    setAmount('')
    setReference('')
    setMethod('cash')
  }

  const canFinish = paid >= total && payments.length > 0
  const takenByPaystack = payments.some((p) => p.paystack_reference)

  const addConfirmedMomo = (charge: PaystackCharge) => {
    setPayments((prev) => [
      ...prev,
      {
        method: 'momo',
        amount: toNumber(charge.amount).toFixed(2),
        momo_network: charge.network,
        reference: charge.reference,
        paystack_reference: charge.reference,
      },
    ])
    setPrompting(null)
    setAmount('')
    setMethod('cash')
    toast.success(`MoMo payment of ${money(charge.amount)} received`)
  }

  const removePayment = (index: number) => {
    if (payments[index].paystack_reference &&
        !window.confirm('This MoMo money has already been received. Remove it from this sale? It will show as unmatched under Reports → Payments.')) return
    setPayments(payments.filter((_, j) => j !== index))
  }

  const close = () => {
    if (takenByPaystack && !window.confirm('MoMo money has already been received for this sale. Close without completing the sale?')) return
    onClose()
  }

  return (
    <Modal open onClose={close} title="Payment" size="lg">
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <div className="mb-3 rounded-xl bg-slate-900 p-4 text-white">
            <div className="text-xs uppercase tracking-wide text-slate-400">Total due</div>
            <div className="text-3xl font-bold">{money(total)}</div>
            <div className="mt-2 flex justify-between text-sm">
              <span>Paid {money(paid)}</span>
              {remaining > 0 ? <span className="text-amber-300">Remaining {money(remaining)}</span> : <span className="text-emerald-300">Change {money(change)}</span>}
            </div>
          </div>
          <div className="mb-3 grid grid-cols-3 gap-2">
            {METHODS.map((m) => (
              <button
                key={m}
                disabled={methodDisabled(m)}
                onClick={() => setMethod(m)}
                className={`rounded-lg border px-2 py-3 text-sm font-semibold transition disabled:opacity-40 ${method === m ? 'border-brand-500 bg-brand-500 text-white' : 'border-slate-200 bg-white hover:bg-slate-50'}`}
              >
                {METHOD_LABELS[m]}
              </button>
            ))}
          </div>
          {method === 'momo' && (
            <div className="mb-3 grid grid-cols-3 gap-2">
              {MOMO_NETWORKS.map((n) => (
                <button
                  key={n.value}
                  onClick={() => setNetwork(n.value)}
                  className={`rounded-lg border py-2 text-xs font-semibold ${network === n.value ? 'border-amber-500 bg-amber-50 text-amber-800' : 'border-slate-200'}`}
                >
                  {n.label}
                </button>
              ))}
            </div>
          )}
          {((method === 'momo' && !usePrompt) || method === 'card' || method === 'bank') && (
            <input
              className="input mb-3"
              placeholder={method === 'momo' ? 'MoMo transaction ID' : 'Reference / approval code'}
              value={reference}
              onChange={(e) => setReference(e.target.value)}
            />
          )}
          {method === 'momo' && paystackMode && (
            <div className="mb-3 text-xs text-slate-600">
              {usePrompt ? 'A payment prompt goes to the customer\'s phone through Paystack. ' : 'Recording a MoMo payment by hand. '}
              <button className="font-semibold text-brand-700 underline" onClick={() => setManualMomo(!manualMomo)}>
                {usePrompt ? 'Record manually instead' : 'Use Paystack prompt'}
              </button>
              {paystackMode !== 'live' && (
                <span className="mt-1 block rounded bg-amber-50 px-2 py-1 font-semibold text-amber-800">
                  Paystack {paystackMode === 'simulated' ? 'simulator' : 'test mode'}: no real money is taken.
                </span>
              )}
            </div>
          )}
          {method === 'credit' && <p className="mb-3 text-xs text-slate-500">Credit available: {money(creditAvailable)}</p>}
          {method === 'points' && (
            <p className="mb-3 text-xs text-slate-500">
              {customer?.loyalty_points} points = {money(pointsWorth)}
            </p>
          )}
          <div className="mb-3 space-y-1">
            {payments.map((p, i) => (
              <div key={i} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm">
                <span>
                  {METHOD_LABELS[p.method]}
                  {p.momo_network && ` · ${p.momo_network.toUpperCase()}`}
                  {p.reference && !p.paystack_reference && ` · ${p.reference}`}
                  {p.paystack_reference && <span className="ml-1 rounded bg-emerald-100 px-1.5 text-xs font-semibold text-emerald-800">✓ Paystack</span>}
                </span>
                <span className="flex items-center gap-2 font-semibold">
                  {money(p.amount)}
                  <button className="text-red-500" onClick={() => removePayment(i)}>
                    ✕
                  </button>
                </span>
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="mb-2 flex h-14 items-center justify-end rounded-lg border border-slate-300 bg-white px-4 text-3xl font-bold">
            {amount || <span className="text-slate-300">{remaining.toFixed(2)}</span>}
          </div>
          {method === 'cash' && remaining > 0 && (
            <div className="mb-2 flex flex-wrap gap-2">
              {quickCash.map((v) => (
                <Button key={v} variant="secondary" size="sm" onClick={() => add(v)}>
                  {v === remaining ? 'Exact' : money(v, false)}
                </Button>
              ))}
            </div>
          )}
          <NumPad value={amount} onChange={setAmount} />
          <div className="mt-2 grid grid-cols-2 gap-2">
            <Button variant="secondary" size="lg" disabled={remaining <= 0 && method !== 'cash'} onClick={() => add()}>
              {usePrompt ? 'Send MoMo prompt' : `Add ${METHOD_LABELS[method]}`}
            </Button>
            <Button
              variant="success"
              size="lg"
              loading={busy}
              disabled={!canFinish}
              onClick={() => onComplete(payments)}
            >
              Complete sale
            </Button>
          </div>
        </div>
      </div>
      {prompting !== null && (
        <MomoPrompt
          amount={prompting}
          phone={customer?.phone ?? ''}
          network={network}
          onConfirmed={addConfirmedMomo}
          onClose={() => setPrompting(null)}
        />
      )}
    </Modal>
  )
}
