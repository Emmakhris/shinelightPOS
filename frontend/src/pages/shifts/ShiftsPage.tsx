import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api/client'
import type { CashMovement, Shift, ShiftReport } from '../../api/types'
import { isCancelled, withApproval } from '../../components/approval'
import { NumPad } from '../../components/NumPad'
import { ShiftReportDoc, printDoc } from '../../components/print'
import { toast } from '../../components/toast'
import { Badge, Button, Empty, Field, Loading, Modal, PageHeader, Stat } from '../../components/ui'
import { METHOD_LABELS, dateTime, money, toNumber } from '../../lib/format'
import { useCurrentShift, useSettings } from '../../lib/hooks'
import { OpenShiftModal } from './OpenShiftModal'

export function ShiftsPage() {
  const current = useCurrentShift()
  const history = useQuery({ queryKey: ['shift', 'history'], queryFn: () => api.get<Shift[]>('/shifts/') })
  const [opening, setOpening] = useState(false)
  const [viewing, setViewing] = useState<Shift | null>(null)

  return (
    <div>
      <PageHeader title="Shifts" subtitle="Open and close the cash drawer, record cash in/out, and print X/Z reports." />
      {current.isLoading ? <Loading /> : current.data ? (
        <CurrentShift shift={current.data} />
      ) : (
        <div className="card mb-6 flex items-center justify-between p-5">
          <div>
            <div className="font-bold">No open shift</div>
            <div className="text-sm text-slate-500">Open a shift with the cash in your drawer before selling.</div>
          </div>
          <Button size="lg" onClick={() => setOpening(true)}>Open shift</Button>
        </div>
      )}
      <h2 className="mb-2 mt-6 text-lg font-bold">Shift history</h2>
      <div className="card overflow-x-auto">
        <table className="table">
          <thead><tr><th>Cashier</th><th>Till</th><th>Opened</th><th>Closed</th><th className="text-right">Expected</th><th className="text-right">Counted</th><th className="text-right">Over / short</th><th></th></tr></thead>
          <tbody>
            {history.data?.map((s) => (
              <tr key={s.id} className="cursor-pointer" onClick={() => setViewing(s)}>
                <td>{s.user_name}</td>
                <td>{s.register_name}</td>
                <td>{dateTime(s.opened_at)}</td>
                <td>{s.closed_at ? dateTime(s.closed_at) : <Badge color="green">Open</Badge>}</td>
                <td className="text-right">{s.expected_cash ? money(s.expected_cash) : ''}</td>
                <td className="text-right">{s.counted_cash ? money(s.counted_cash) : ''}</td>
                <td className={`text-right font-semibold ${toNumber(s.difference) < 0 ? 'text-red-600' : toNumber(s.difference) > 0 ? 'text-amber-600' : ''}`}>
                  {s.difference !== null ? money(s.difference) : ''}
                </td>
                <td className="text-right text-xs text-brand-700">Report</td>
              </tr>
            ))}
          </tbody>
        </table>
        {history.data?.length === 0 && <Empty>No shifts yet.</Empty>}
      </div>
      {opening && <OpenShiftModal onClose={() => setOpening(false)} />}
      {viewing && <ReportModal shift={viewing} onClose={() => setViewing(null)} />}
    </div>
  )
}

function CurrentShift({ shift }: { shift: Shift }) {
  const qc = useQueryClient()
  const settings = useSettings().data
  const report = useQuery({ queryKey: ['shift', 'report', shift.id], queryFn: () => api.get<ShiftReport>(`/shifts/${shift.id}/report/`) })
  const movements = useQuery({ queryKey: ['shift', 'movements', shift.id], queryFn: () => api.get<CashMovement[]>(`/shifts/${shift.id}/cash-movements/`) })
  const [cashDialog, setCashDialog] = useState<CashMovement['kind'] | null>(null)
  const [closing, setClosing] = useState(false)
  const r = report.data

  const printX = () => r && settings && printDoc(<ShiftReportDoc report={r} settings={settings} title="X REPORT" />, settings.receipt_width)

  return (
    <div className="mb-6">
      <div className="card mb-3 flex flex-wrap items-center justify-between gap-3 p-4">
        <div>
          <div className="font-bold">{shift.register_name} · open since {dateTime(shift.opened_at)}</div>
          <div className="text-sm text-slate-500">Opened with {money(shift.opening_float)}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => setCashDialog('paid_in')}>Cash in</Button>
          <Button variant="secondary" onClick={() => setCashDialog('paid_out')}>Cash out</Button>
          <Button variant="secondary" onClick={() => setCashDialog('drop')}>Drop to safe</Button>
          <Button variant="secondary" onClick={printX}>Print X report</Button>
          <Button variant="danger" onClick={() => setClosing(true)}>Close shift</Button>
        </div>
      </div>
      {r && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Sales" value={money(r.gross_sales)} sub={`${r.sales_count} sales`} />
          <Stat label="Cash expected in drawer" value={money(r.expected_cash)} />
          {Object.entries(r.payments).map(([m, v]) => <Stat key={m} label={METHOD_LABELS[m] ?? m} value={money(v)} />)}
          <Stat label="Refunds" value={money(r.refunds)} />
        </div>
      )}
      {(movements.data?.length ?? 0) > 0 && (
        <div className="card mt-3 p-3">
          <div className="label">Cash movements</div>
          {movements.data?.map((m) => (
            <div key={m.id} className="flex justify-between border-b border-slate-100 py-1 text-sm last:border-0">
              <span>{m.kind_label} · {m.reason} · {m.user_name}</span>
              <span className="font-semibold">{m.kind === 'paid_in' ? '+' : '−'}{money(m.amount)}</span>
            </div>
          ))}
        </div>
      )}
      {cashDialog && <CashMovementModal shift={shift} kind={cashDialog} onClose={() => setCashDialog(null)} />}
      {closing && r && (
        <CloseShiftModal
          shift={shift}
          expected={r.expected_cash ?? '0'}
          onClose={() => setClosing(false)}
          onClosed={(z) => {
            setClosing(false)
            qc.invalidateQueries({ queryKey: ['shift'] })
            if (settings) printDoc(<ShiftReportDoc report={z} settings={settings} title="Z REPORT" />, settings.receipt_width)
          }}
        />
      )}
    </div>
  )
}

const KIND_TITLES = { paid_in: 'Cash in', paid_out: 'Cash out (expense)', drop: 'Cash drop to safe' }

function CashMovementModal({ shift, kind, onClose }: { shift: Shift; kind: CashMovement['kind']; onClose: () => void }) {
  const qc = useQueryClient()
  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true)
    try {
      await withApproval((pin) => api.post(`/shifts/${shift.id}/cash-movements/`, { kind, amount, reason, approval_pin: pin }))
      qc.invalidateQueries({ queryKey: ['shift'] })
      onClose()
    } catch (err) {
      if (!isCancelled(err)) toast.error(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open size="sm" onClose={onClose} title={KIND_TITLES[kind]} footer={<Button loading={busy} disabled={!toNumber(amount) || !reason} onClick={save}>Save</Button>}>
      <Field label="Reason" className="mb-3"><input className="input" autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder={kind === 'paid_out' ? 'e.g. Bought water' : ''} /></Field>
      <div className="mb-2 flex h-12 items-center justify-end rounded-lg border px-3 text-2xl font-bold">{amount || '0.00'}</div>
      <NumPad value={amount} onChange={setAmount} />
    </Modal>
  )
}

function CloseShiftModal({ shift, expected, onClose, onClosed }: { shift: Shift; expected: string; onClose: () => void; onClosed: (z: ShiftReport) => void }) {
  const [counted, setCounted] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const diff = toNumber(counted) - toNumber(expected)
  const close = async () => {
    setBusy(true)
    try {
      onClosed(await api.post<ShiftReport>(`/shifts/${shift.id}/close/`, { counted_cash: counted, note }))
      toast.success('Shift closed')
    } catch (err) {
      toast.error(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open size="sm" onClose={onClose} title="Close shift" footer={<Button variant="danger" loading={busy} disabled={counted === ''} onClick={close}>Close & print Z report</Button>}>
      <p className="mb-2 text-sm text-slate-600">Count all the cash in the drawer and enter the total.</p>
      <div className="mb-2 flex h-12 items-center justify-end rounded-lg border px-3 text-2xl font-bold">{counted || '0.00'}</div>
      <NumPad value={counted} onChange={setCounted} />
      {counted !== '' && (
        <p className={`mt-3 text-center font-semibold ${diff < 0 ? 'text-red-600' : diff > 0 ? 'text-amber-600' : 'text-emerald-600'}`}>
          {diff === 0 ? 'Drawer balances exactly ✓' : `${diff < 0 ? 'Short' : 'Over'} by ${money(Math.abs(diff))}`}
        </p>
      )}
      <Field label="Note" className="mt-3"><input className="input" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
    </Modal>
  )
}

function ReportModal({ shift, onClose }: { shift: Shift; onClose: () => void }) {
  const settings = useSettings().data
  const report = useQuery({ queryKey: ['shift', 'report', shift.id], queryFn: () => api.get<ShiftReport>(`/shifts/${shift.id}/report/`) })
  const r = report.data
  const title = shift.status === 'closed' ? 'Z REPORT' : 'X REPORT'
  return (
    <Modal open onClose={onClose} title={`${shift.user_name} · ${dateTime(shift.opened_at)}`}
      footer={r && settings && <Button onClick={() => printDoc(<ShiftReportDoc report={r} settings={settings} title={title} />, settings.receipt_width)}>🖨 Print {title}</Button>}>
      {!r || !settings ? <Loading /> : (
        <div className="mx-auto max-w-xs rounded border border-slate-200 bg-white">
          <ShiftReportDoc report={r} settings={settings} title={title} />
        </div>
      )}
    </Modal>
  )
}
