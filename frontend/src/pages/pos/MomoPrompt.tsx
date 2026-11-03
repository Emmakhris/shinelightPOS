import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import type { PaystackCharge } from '../../api/types'
import { Button, Modal, Spinner } from '../../components/ui'
import { MOMO_NETWORKS, money } from '../../lib/format'

const APPROVAL_SECONDS = 180 // the networks cancel unapproved prompts after this
const POLL_MS = 4000

/**
 * Sends a Paystack MoMo prompt to the customer's phone and waits until they approve it.
 * Calls onConfirmed only once the server has seen Paystack report success.
 */
export function MomoPrompt({ amount, phone: initialPhone, network: initialNetwork, onConfirmed, onClose }: {
  amount: number
  phone: string
  network: string
  onConfirmed: (charge: PaystackCharge) => void
  onClose: () => void
}) {
  const [phone, setPhone] = useState(initialPhone)
  const [network, setNetwork] = useState(initialNetwork)
  const [charge, setCharge] = useState<PaystackCharge | null>(null)
  const [error, setError] = useState('')
  const [otp, setOtp] = useState('')
  const [busy, setBusy] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const done = useRef(false)

  const waiting = charge && ['pending', 'pay_offline', 'send_otp'].includes(charge.status)

  // Poll Paystack (through our server) while the customer approves on their phone.
  useEffect(() => {
    if (!charge || !['pending', 'pay_offline'].includes(charge.status)) return
    const started = Date.now()
    const tick = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000)
    const poll = window.setInterval(async () => {
      try {
        const latest = await api.get<PaystackCharge>(`/payments/momo/${charge.reference}/`)
        setCharge(latest)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Could not check the payment.')
      }
    }, POLL_MS)
    return () => {
      window.clearInterval(tick)
      window.clearInterval(poll)
    }
  }, [charge?.reference, charge?.status]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (charge?.status === 'success' && !done.current) {
      done.current = true
      onConfirmed(charge)
    }
  }, [charge, onConfirmed])

  const send = async () => {
    setBusy(true)
    setError('')
    setElapsed(0)
    try {
      setCharge(await api.post<PaystackCharge>('/payments/momo/', { amount: amount.toFixed(2), phone, network }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not send the prompt.')
    } finally {
      setBusy(false)
    }
  }

  const submitOtp = async () => {
    if (!charge) return
    setBusy(true)
    try {
      setCharge(await api.post<PaystackCharge>(`/payments/momo/${charge.reference}/otp/`, { otp }))
      setOtp('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Code not accepted.')
    } finally {
      setBusy(false)
    }
  }

  const checkNow = async () => {
    if (!charge) return
    try {
      setCharge(await api.get<PaystackCharge>(`/payments/momo/${charge.reference}/?force=1`))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not check the payment.')
    }
  }

  const cancel = async () => {
    if (charge && waiting) {
      if (!window.confirm('Stop waiting for this MoMo payment? If the customer approves later it will show under Reports → Payments.')) return
      await api.post(`/payments/momo/${charge.reference}/cancel/`).catch(() => undefined)
    }
    onClose()
  }

  const remaining = Math.max(APPROVAL_SECONDS - elapsed, 0)

  return (
    <Modal open size="sm" onClose={cancel} title={`MoMo prompt · ${money(amount)}`}>
      {!charge || charge.status === 'failed' || charge.status === 'abandoned' ? (
        <div className="space-y-3">
          {charge?.status === 'failed' && (
            <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">Payment failed: {charge.message || 'not approved'}.</p>
          )}
          <label className="block">
            <span className="label">Customer's MoMo number</span>
            <input className="input text-lg" autoFocus inputMode="tel" placeholder="024 123 4567" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </label>
          <div className="grid grid-cols-3 gap-2">
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
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button size="lg" className="w-full" loading={busy} disabled={phone.replace(/\D/g, '').length < 10} onClick={send}>
            {charge ? 'Try again' : 'Send prompt to phone'}
          </Button>
        </div>
      ) : charge.status === 'send_otp' ? (
        <div className="space-y-3">
          <p className="text-sm text-slate-600">{charge.display_text || 'Ask the customer for the code sent to their phone.'}</p>
          <input className="input text-center text-2xl tracking-widest" autoFocus inputMode="numeric" value={otp} onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))} />
          {charge.message && <p className="text-sm text-red-600">{charge.message}</p>}
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button size="lg" className="w-full" loading={busy} disabled={!otp} onClick={submitOtp}>Submit code</Button>
        </div>
      ) : charge.status === 'success' ? (
        <div className="py-6 text-center">
          <div className="text-5xl">✅</div>
          <p className="mt-2 font-semibold text-emerald-700">Payment received</p>
        </div>
      ) : (
        <div className="space-y-4 py-2 text-center">
          <Spinner />
          <div>
            <p className="font-semibold">Waiting for the customer to approve…</p>
            <p className="text-sm text-slate-600">{charge.display_text || 'Ask the customer to check their phone and enter their MoMo PIN.'}</p>
            <p className="mt-1 text-xs text-slate-500">{charge.phone} · {MOMO_NETWORKS.find((n) => n.value === charge.network)?.label}</p>
          </div>
          <div className="text-3xl font-black tabular-nums text-slate-700">
            {Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, '0')}
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="grid grid-cols-2 gap-2">
            <Button variant="secondary" onClick={checkNow}>Check now</Button>
            <Button variant="ghost" onClick={cancel}>Stop waiting</Button>
          </div>
        </div>
      )}
    </Modal>
  )
}
