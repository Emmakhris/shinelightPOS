import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, qs } from '../../api/client'
import type { AuditEntry, Paginated, Role, User } from '../../api/types'
import { toast } from '../../components/toast'
import { Badge, Button, Empty, Field, Loading, Modal, PageHeader, Tabs, Toggle } from '../../components/ui'
import { dateTime, titleCase } from '../../lib/format'
import { useAuth } from '../../stores/auth'

const ROLE_HELP: Record<Role, string> = {
  owner: 'Everything, including settings, staff and taxes.',
  manager: 'Catalogue, stock, refunds, voids, discounts, reports. Approves with PIN.',
  cashier: 'Sells, takes payments, manages customers, cash in/out.',
  waiter: 'Takes table orders and payments.',
}

export function UsersPage() {
  const can = useAuth((s) => s.can)
  const [tab, setTab] = useState<'staff' | 'audit'>(can('manage_users') ? 'staff' : 'audit')
  const tabs = [
    ...(can('manage_users') ? [{ value: 'staff' as const, label: 'Staff' }] : []),
    ...(can('view_audit') ? [{ value: 'audit' as const, label: 'Activity log' }] : []),
  ]
  return (
    <div>
      <PageHeader title="Staff" subtitle="Who can use the system, and what they did." />
      <Tabs value={tab} onChange={setTab} tabs={tabs} />
      {tab === 'staff' && <Staff />}
      {tab === 'audit' && <Audit />}
    </div>
  )
}

function Staff() {
  const users = useQuery({ queryKey: ['users'], queryFn: () => api.get<User[]>('/users/') })
  const [edit, setEdit] = useState<Partial<User> | null>(null)
  return (
    <>
      <div className="mb-3 flex justify-end"><Button onClick={() => setEdit({ role: 'cashier', is_active: true })}>+ Add staff</Button></div>
      <div className="card overflow-x-auto">
        {users.isLoading ? <Loading /> : (
          <table className="table">
            <thead><tr><th>Name</th><th>Username</th><th>Role</th><th>PIN</th><th>Last sign in</th><th>Status</th></tr></thead>
            <tbody>
              {users.data?.map((u) => (
                <tr key={u.id} className="cursor-pointer" onClick={() => setEdit(u)}>
                  <td className="font-semibold">{u.display_name}</td>
                  <td>{u.username}</td>
                  <td className="capitalize">{u.role}</td>
                  <td>{u.has_pin ? '✓' : '—'}</td>
                  <td>{dateTime(u.last_login)}</td>
                  <td>{u.is_active ? <Badge color="green">Active</Badge> : <Badge color="red">Disabled</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {edit && <UserForm user={edit} onClose={() => setEdit(null)} />}
    </>
  )
}

function UserForm({ user, onClose }: { user: Partial<User>; onClose: () => void }) {
  const qc = useQueryClient()
  const me = useAuth((s) => s.user)
  const [u, setU] = useState<Partial<User>>(user)
  const [password, setPassword] = useState('')
  const [pin, setPin] = useState('')
  const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true)
    try {
      const body = {
        username: u.username, first_name: u.first_name ?? '', last_name: u.last_name ?? '', email: u.email ?? '', phone: u.phone ?? '',
        role: u.role, is_active: u.is_active, ...(password ? { password } : {}), ...(pin ? { pin } : {}),
      }
      if (u.id) await api.patch(`/users/${u.id}/`, body)
      else await api.post('/users/', body)
      qc.invalidateQueries({ queryKey: ['users'] })
      toast.success('Saved')
      onClose()
    } catch (err) {
      toast.error(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open onClose={onClose} title={u.id ? `Edit ${u.display_name}` : 'Add staff member'} footer={<Button loading={busy} disabled={!u.username || (!u.id && password.length < 6)} onClick={save}>Save</Button>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="First name"><input className="input" value={u.first_name ?? ''} onChange={(e) => setU({ ...u, first_name: e.target.value })} /></Field>
        <Field label="Last name"><input className="input" value={u.last_name ?? ''} onChange={(e) => setU({ ...u, last_name: e.target.value })} /></Field>
        <Field label="Username"><input className="input" value={u.username ?? ''} onChange={(e) => setU({ ...u, username: e.target.value.trim() })} /></Field>
        <Field label="Phone"><input className="input" value={u.phone ?? ''} onChange={(e) => setU({ ...u, phone: e.target.value })} /></Field>
        <Field label={u.id ? 'New password (leave blank to keep)' : 'Password'} hint="At least 6 characters">
          <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
        </Field>
        <Field label={u.id && u.has_pin ? 'New PIN (leave blank to keep)' : 'PIN (4–6 digits)'}>
          <input className="input" inputMode="numeric" value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 6))} />
        </Field>
        <Field label="Role" className="sm:col-span-2" hint={u.role ? ROLE_HELP[u.role] : ''}>
          <select className="input" value={u.role} onChange={(e) => setU({ ...u, role: e.target.value as Role })}>
            {(['cashier', 'waiter', 'manager', 'owner'] as Role[]).map((r) => <option key={r} value={r}>{titleCase(r)}</option>)}
          </select>
        </Field>
        {u.id && u.id !== me?.id && <Toggle checked={!!u.is_active} onChange={(v) => setU({ ...u, is_active: v })} label="Can sign in" />}
      </div>
    </Modal>
  )
}

function Audit() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const data = useQuery({
    queryKey: ['audit', page, search],
    queryFn: () => api.get<Paginated<AuditEntry>>(`/audit-log/${qs({ page, search })}`),
    placeholderData: keepPreviousData,
  })
  return (
    <>
      <input className="input mb-3 max-w-xs" placeholder="Search action" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
      <div className="card overflow-x-auto">
        <table className="table">
          <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Approved by</th><th>Details</th></tr></thead>
          <tbody>
            {data.data?.results.map((a) => (
              <tr key={a.id}>
                <td className="whitespace-nowrap">{dateTime(a.created_at)}</td>
                <td>{a.user_name}</td>
                <td className="font-semibold">{titleCase(a.action)}</td>
                <td>{a.approved_by_name}</td>
                <td className="max-w-md truncate font-mono text-xs text-slate-500" title={JSON.stringify(a.details)}>
                  {Object.entries(a.details).map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`).join(' · ')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.data?.count === 0 && <Empty>No activity yet.</Empty>}
      </div>
      {data.data && data.data.count > 50 && (
        <div className="mt-3 flex justify-end gap-2">
          <Button size="sm" variant="secondary" disabled={!data.data.previous} onClick={() => setPage(page - 1)}>Previous</Button>
          <Button size="sm" variant="secondary" disabled={!data.data.next} onClick={() => setPage(page + 1)}>Next</Button>
        </div>
      )}
    </>
  )
}
