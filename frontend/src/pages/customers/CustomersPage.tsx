import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, qs } from '../../api/client'
import type { Customer, CustomerTransaction, SaleSummary } from '../../api/types'
import { toast } from '../../components/toast'
import { Button, Empty, Field, Loading, Modal, PageHeader, Tabs, Toggle } from '../../components/ui'
import { dateTime, money, toNumber } from '../../lib/format'
import { useAuth } from '../../stores/auth'
import { SaleDetailModal } from '../sales/SalesPage'

export function CustomersPage() {
  const [search, setSearch] = useState('')
  const [owing, setOwing] = useState(false)
  const [editing, setEditing] = useState<Partial<Customer> | null>(null)
  const [viewing, setViewing] = useState<Customer | null>(null)
  const can = useAuth((s) => s.can)
  const customers = useQuery({
    queryKey: ['customers', 'list', search, owing],
    queryFn: () => api.get<Customer[]>(`/customers/${qs({ search, owing: owing ? 1 : undefined, is_active: true })}`),
  })

  return (
    <div>
      <PageHeader
        title="Customers"
        subtitle="Loyalty points, credit accounts and purchase history."
        actions={can('manage_customers') && <Button onClick={() => setEditing({ name: '', phone: '', credit_limit: '0' })}>+ New customer</Button>}
      />
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <input className="input max-w-xs" placeholder="Search name or phone" value={search} onChange={(e) => setSearch(e.target.value)} />
        <Toggle checked={owing} onChange={setOwing} label="Only customers who owe" />
      </div>
      <div className="card overflow-x-auto">
        {customers.isLoading ? <Loading /> : (
          <table className="table">
            <thead><tr><th>Name</th><th>Phone</th><th className="text-right">Points</th><th className="text-right">Credit limit</th><th className="text-right">Owes</th></tr></thead>
            <tbody>
              {customers.data?.map((c) => (
                <tr key={c.id} className="cursor-pointer" onClick={() => setViewing(c)}>
                  <td className="font-semibold">{c.name}</td>
                  <td>{c.phone}</td>
                  <td className="text-right">{c.loyalty_points}</td>
                  <td className="text-right">{toNumber(c.credit_limit) ? money(c.credit_limit) : '—'}</td>
                  <td className={`text-right font-semibold ${toNumber(c.balance) > 0 ? 'text-red-600' : ''}`}>{toNumber(c.balance) ? money(c.balance) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {customers.data?.length === 0 && <Empty>No customers found.</Empty>}
      </div>
      {editing && <CustomerForm customer={editing} onClose={() => setEditing(null)} />}
      {viewing && <CustomerDetail id={viewing.id} onClose={() => setViewing(null)} onEdit={(c) => { setViewing(null); setEditing(c) }} />}
    </div>
  )
}

function CustomerForm({ customer, onClose }: { customer: Partial<Customer>; onClose: () => void }) {
  const qc = useQueryClient()
  const [c, setC] = useState(customer)
  const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true)
    try {
      const body = { name: c.name, phone: c.phone, email: c.email ?? '', address: c.address ?? '', notes: c.notes ?? '', credit_limit: c.credit_limit || '0' }
      if (c.id) await api.patch(`/customers/${c.id}/`, body)
      else await api.post('/customers/', body)
      qc.invalidateQueries({ queryKey: ['customers'] })
      onClose()
    } catch (err) {
      toast.error(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open onClose={onClose} title={c.id ? 'Edit customer' : 'New customer'} footer={<Button loading={busy} disabled={!c.name} onClick={save}>Save</Button>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name"><input className="input" autoFocus value={c.name ?? ''} onChange={(e) => setC({ ...c, name: e.target.value })} /></Field>
        <Field label="Phone"><input className="input" inputMode="tel" value={c.phone ?? ''} onChange={(e) => setC({ ...c, phone: e.target.value })} /></Field>
        <Field label="Email"><input className="input" type="email" value={c.email ?? ''} onChange={(e) => setC({ ...c, email: e.target.value })} /></Field>
        <Field label="Credit limit" hint="How much they may owe. 0 = no credit."><input className="input" inputMode="decimal" value={c.credit_limit ?? '0'} onChange={(e) => setC({ ...c, credit_limit: e.target.value })} /></Field>
        <Field label="Address" className="sm:col-span-2"><textarea className="input" rows={2} value={c.address ?? ''} onChange={(e) => setC({ ...c, address: e.target.value })} /></Field>
        <Field label="Notes" className="sm:col-span-2"><textarea className="input" rows={2} value={c.notes ?? ''} onChange={(e) => setC({ ...c, notes: e.target.value })} /></Field>
      </div>
    </Modal>
  )
}

function CustomerDetail({ id, onClose, onEdit }: { id: number; onClose: () => void; onEdit: (c: Customer) => void }) {
  const qc = useQueryClient()
  const [tab, setTab] = useState<'sales' | 'account'>('sales')
  const [paying, setPaying] = useState(false)
  const [saleId, setSaleId] = useState<number | null>(null)
  const customer = useQuery({ queryKey: ['customers', 'one', id], queryFn: () => api.get<Customer>(`/customers/${id}/`) })
  const sales = useQuery({ queryKey: ['customers', 'sales', id], queryFn: () => api.get<SaleSummary[]>(`/customers/${id}/sales/`) })
  const tx = useQuery({ queryKey: ['customers', 'tx', id], queryFn: () => api.get<CustomerTransaction[]>(`/customers/${id}/transactions/`) })
  const c = customer.data
  return (
    <Modal open size="lg" onClose={onClose} title={c?.name ?? 'Customer'}
      footer={c && (
        <>
          <Button variant="secondary" className="mr-auto" onClick={() => onEdit(c)}>Edit</Button>
          {toNumber(c.balance) > 0 && <Button onClick={() => setPaying(true)}>Record payment</Button>}
        </>
      )}>
      {!c ? <Loading /> : (
        <>
          <div className="mb-4 grid grid-cols-3 gap-3 text-center">
            <div className="rounded-lg bg-slate-50 p-3"><div className="label">Points</div><div className="text-xl font-bold">{c.loyalty_points}</div></div>
            <div className="rounded-lg bg-slate-50 p-3"><div className="label">Owes</div><div className={`text-xl font-bold ${toNumber(c.balance) ? 'text-red-600' : ''}`}>{money(c.balance)}</div></div>
            <div className="rounded-lg bg-slate-50 p-3"><div className="label">Credit limit</div><div className="text-xl font-bold">{money(c.credit_limit)}</div></div>
          </div>
          <p className="mb-3 text-sm text-slate-600">{c.phone} {c.email && `· ${c.email}`}</p>
          <Tabs value={tab} onChange={setTab} tabs={[{ value: 'sales', label: 'Purchases' }, { value: 'account', label: 'Account history' }]} />
          {tab === 'sales' && (
            <table className="table">
              <tbody>
                {sales.data?.map((s) => (
                  <tr key={s.id} className="cursor-pointer" onClick={() => setSaleId(s.id)}>
                    <td className="font-mono text-xs">{s.invoice_number}</td><td>{dateTime(s.created_at)}</td><td>{s.status_label}</td><td className="text-right font-semibold">{money(s.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {tab === 'account' && (
            <table className="table">
              <thead><tr><th>When</th><th>What</th><th className="text-right">Balance change</th><th className="text-right">Points</th></tr></thead>
              <tbody>
                {tx.data?.map((t) => (
                  <tr key={t.id}>
                    <td>{dateTime(t.created_at)}</td>
                    <td>{t.kind_label}{t.invoice_number && ` · ${t.invoice_number}`}{t.method && ` · ${t.method}`}{t.note && <div className="text-xs text-slate-500">{t.note}</div>}</td>
                    <td className="text-right">{toNumber(t.amount) ? money(t.amount) : ''}</td>
                    <td className="text-right">{toNumber(t.points) ? t.points : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {(tab === 'sales' ? sales.data : tx.data)?.length === 0 && <Empty>Nothing yet.</Empty>}
        </>
      )}
      {paying && c && <PayBalanceModal customer={c} onClose={() => setPaying(false)} onDone={() => { setPaying(false); qc.invalidateQueries({ queryKey: ['customers'] }) }} />}
      {saleId && <SaleDetailModal id={saleId} onClose={() => setSaleId(null)} />}
    </Modal>
  )
}

function PayBalanceModal({ customer, onClose, onDone }: { customer: Customer; onClose: () => void; onDone: () => void }) {
  const [amount, setAmount] = useState(customer.balance)
  const [method, setMethod] = useState('cash')
  const [reference, setReference] = useState('')
  const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true)
    try {
      await api.post(`/customers/${customer.id}/pay_balance/`, { amount, method, reference })
      toast.success('Payment recorded')
      onDone()
    } catch (err) {
      toast.error(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open size="sm" onClose={onClose} title={`Payment from ${customer.name}`} footer={<Button loading={busy} onClick={save}>Record payment</Button>}>
      <p className="mb-3 text-sm">Owes {money(customer.balance)}</p>
      <div className="space-y-3">
        <Field label="Amount"><input className="input" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
        <Field label="Paid by">
          <select className="input" value={method} onChange={(e) => setMethod(e.target.value)}>
            <option value="cash">Cash</option><option value="momo">Mobile Money</option><option value="card">Card</option><option value="bank">Bank transfer</option>
          </select>
        </Field>
        <Field label="Reference"><input className="input" value={reference} onChange={(e) => setReference(e.target.value)} /></Field>
      </div>
    </Modal>
  )
}
