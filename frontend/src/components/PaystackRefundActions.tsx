import { useState } from 'react'
import { api } from '../api/client'
import type { PaystackRefund } from '../api/types'
import { isCancelled, withApproval } from './approval'
import { toast } from './toast'
import { Badge, Button } from './ui'

const COLORS: Record<PaystackRefund['status'], 'green' | 'red' | 'amber' | 'gray'> = {
  sending: 'amber',
  pending: 'amber',
  processing: 'amber',
  'needs-attention': 'red',
  processed: 'green',
  failed: 'red',
  settled: 'gray',
}

/** Status of a refund going back through Paystack, and what can be done about it. */
export function PaystackRefundActions({ refund, onChange }: { refund: PaystackRefund; onChange: () => void }) {
  const [busy, setBusy] = useState(false)
  const run = async (action: (pin?: string) => Promise<unknown>) => {
    setBusy(true)
    try {
      await withApproval(action)
      onChange()
    } catch (err) {
      if (!isCancelled(err)) toast.error(err)
    } finally {
      setBusy(false)
    }
  }
  const url = `/payments/refunds/${refund.reference}`
  const settle = () => {
    const note = window.prompt('How was the customer paid? For example: cash, or a direct MoMo transfer.')
    if (note) run((pin) => api.post(`${url}/settle/`, { note, approval_pin: pin }))
  }
  const open = refund.status === 'sending' || refund.status === 'pending' || refund.status === 'processing' || refund.status === 'needs-attention'

  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <Badge color={COLORS[refund.status]}>{refund.status_label}</Badge>
      {refund.status === 'processed' && <span className="text-xs text-slate-500">Can take up to 10 business days to arrive.</span>}
      {refund.message && <span className="text-xs text-slate-500">{refund.message}</span>}
      {open && <Button size="sm" variant="ghost" loading={busy} onClick={() => run(() => api.post(`${url}/check/`, {}))}>Check status</Button>}
      {refund.status === 'failed' && (
        <>
          <Button size="sm" variant="secondary" loading={busy} onClick={() => run((pin) => api.post(`${url}/retry/`, { approval_pin: pin }))}>Try again</Button>
          <Button size="sm" variant="ghost" loading={busy} onClick={settle}>Paid by hand</Button>
        </>
      )}
    </span>
  )
}
