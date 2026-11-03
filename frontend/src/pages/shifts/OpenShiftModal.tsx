import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api/client'
import { NumPad } from '../../components/NumPad'
import { toast } from '../../components/toast'
import { Button, Field, Modal } from '../../components/ui'

export function OpenShiftModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [float, setFloat] = useState('')
  const [register, setRegister] = useState(() => localStorage.getItem('slpos.register') || 'Till 1')
  const [busy, setBusy] = useState(false)

  const open = async () => {
    setBusy(true)
    try {
      localStorage.setItem('slpos.register', register)
      await api.post('/shifts/open/', { opening_float: float || '0', register_name: register })
      await qc.invalidateQueries({ queryKey: ['shift'] })
      toast.success('Shift opened')
      onClose()
    } catch (err) {
      toast.error(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open size="sm" onClose={onClose} title="Open shift">
      <Field label="Till / register name" className="mb-3">
        <input className="input" value={register} onChange={(e) => setRegister(e.target.value)} />
      </Field>
      <span className="label">Opening cash in drawer (float)</span>
      <div className="mb-2 flex h-12 items-center justify-end rounded-lg border px-3 text-2xl font-bold">{float || '0.00'}</div>
      <NumPad value={float} onChange={setFloat} />
      <Button className="mt-3 w-full" size="lg" loading={busy} onClick={open}>
        Open shift
      </Button>
    </Modal>
  )
}
