import { useState } from 'react'
import { create } from 'zustand'
import { ApiError } from '../api/client'
import { NumPad } from './NumPad'
import { Button, Modal } from './ui'

/**
 * Some actions (refunds, big discounts, voids...) need a manager. The server answers
 * 403 with code "approval_required"; we then ask for a manager PIN and retry once with it.
 */

interface Pending {
  message: string
  error?: string
  submit: (pin: string) => void
  cancel: () => void
}

const useApprovalStore = create<{ pending: Pending | null; set: (p: Pending | null) => void }>((set) => ({
  pending: null,
  set: (pending) => set({ pending }),
}))

export class ApprovalCancelled extends Error {
  constructor() {
    super('Cancelled')
  }
}

export async function withApproval<T>(action: (pin?: string) => Promise<T>): Promise<T> {
  try {
    return await action(undefined)
  } catch (err) {
    if (!(err instanceof ApiError) || err.code !== 'approval_required') throw err
    let message = err.message
    // Keep asking until a valid PIN is entered or the cashier cancels.
    for (;;) {
      const pin = await new Promise<string | null>((resolve) => {
        useApprovalStore.getState().set({
          message,
          error: undefined,
          submit: (p) => resolve(p),
          cancel: () => resolve(null),
        })
      })
      if (pin === null) {
        useApprovalStore.getState().set(null)
        throw new ApprovalCancelled()
      }
      try {
        const result = await action(pin)
        useApprovalStore.getState().set(null)
        return result
      } catch (retryErr) {
        if (retryErr instanceof ApiError && retryErr.code === 'approval_required') {
          message = 'That PIN was not accepted. ' + retryErr.message
          continue
        }
        useApprovalStore.getState().set(null)
        throw retryErr
      }
    }
  }
}

export function ApprovalDialog() {
  const pending = useApprovalStore((s) => s.pending)
  const [pin, setPin] = useState('')
  if (!pending) return null
  const submit = () => {
    if (!pin) return
    pending.submit(pin)
    setPin('')
  }
  return (
    <Modal
      open
      size="sm"
      title="Manager approval"
      onClose={() => {
        setPin('')
        pending.cancel()
      }}
    >
      <p className="mb-3 text-sm text-slate-600">{pending.message}</p>
      <input
        autoFocus
        type="password"
        inputMode="numeric"
        className="input mb-3 text-center text-2xl tracking-[0.5em]"
        value={pin}
        placeholder="PIN"
        onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 6))}
        onKeyDown={(e) => e.key === 'Enter' && submit()}
      />
      <NumPad value={pin} onChange={(v) => setPin(v.slice(0, 6))} allowDecimal={false} />
      <Button className="mt-3 w-full" size="lg" onClick={submit} disabled={!pin}>
        Approve
      </Button>
    </Modal>
  )
}

/** Report an error unless the user simply cancelled the approval prompt. */
export function isCancelled(err: unknown) {
  return err instanceof ApprovalCancelled
}
