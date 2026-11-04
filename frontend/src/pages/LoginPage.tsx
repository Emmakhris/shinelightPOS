import { useQuery } from '@tanstack/react-query'
import { useState, type FormEvent, type ReactNode } from 'react'
import { api } from '../api/client'
import { NumPad } from '../components/NumPad'
import { Button, Field } from '../components/ui'
import { useAuth } from '../stores/auth'

interface PinUser {
  id: number
  display_name: string
  role: string
}

function Shell({ children, title }: { children: ReactNode; title: string }) {
  return (
    <div className="flex min-h-full items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-brand-900 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
        <div className="mb-5 flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-brand-500 text-xl font-black text-white">S</span>
          <div>
            <div className="text-lg font-bold">{title}</div>
            <div className="text-xs text-slate-500">ShineLight POS</div>
          </div>
        </div>
        {children}
      </div>
    </div>
  )
}

function PinPad({ onDone }: { onDone?: () => void }) {
  const pinLogin = useAuth((s) => s.pinLogin)
  const users = useQuery({ queryKey: ['pin-users'], queryFn: () => api.get<PinUser[]>('/auth/pin-users/') })
  const [selected, setSelected] = useState<PinUser | null>(null)
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (value = pin) => {
    if (!selected || value.length < 4) return
    setBusy(true)
    setError('')
    try {
      await pinLogin(selected.id, value)
      onDone?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Wrong PIN')
      setPin('')
    } finally {
      setBusy(false)
    }
  }

  if (!selected) {
    return (
      <div className="grid grid-cols-2 gap-2">
        {users.data?.map((u) => (
          <button
            key={u.id}
            onClick={() => setSelected(u)}
            className="rounded-xl border border-slate-200 p-3 text-left transition hover:border-brand-400 hover:bg-brand-50"
          >
            <div className="font-semibold">{u.display_name}</div>
            <div className="text-xs capitalize text-slate-500">{u.role}</div>
          </button>
        ))}
        {users.data?.length === 0 && <p className="col-span-2 text-sm text-slate-500">No staff have a PIN yet. Sign in with a password.</p>}
      </div>
    )
  }
  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <div className="font-semibold">{selected.display_name}</div>
        <button className="text-sm text-brand-600" onClick={() => { setSelected(null); setPin('') }}>
          Change
        </button>
      </div>
      <div className="mb-3 flex h-12 items-center justify-center rounded-lg bg-slate-100 text-3xl tracking-[0.6em]">
        {'•'.repeat(pin.length) || <span className="text-base tracking-normal text-slate-400">Enter PIN</span>}
      </div>
      {error && <p className="mb-2 text-center text-sm text-red-600">{error}</p>}
      <NumPad
        value={pin}
        allowDecimal={false}
        keepLeadingZeros
        onChange={(v) => setPin(v.slice(0, 6))}
        onEnter={() => submit()}
      />
      {busy && <p className="mt-2 text-center text-sm text-slate-500">Checking…</p>}
    </div>
  )
}

export function LoginPage({ businessName }: { businessName?: string }) {
  const login = useAuth((s) => s.login)
  const [mode, setMode] = useState<'pin' | 'password'>('pin')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(username, password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign in failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Shell title={businessName || 'Sign in'}>
      <div className="mb-4 grid grid-cols-2 rounded-lg bg-slate-100 p-1 text-sm font-semibold">
        {(['pin', 'password'] as const).map((m) => (
          <button key={m} onClick={() => setMode(m)} className={`rounded-md py-2 ${mode === m ? 'bg-white shadow' : 'text-slate-500'}`}>
            {m === 'pin' ? 'Quick PIN' : 'Username & password'}
          </button>
        ))}
      </div>
      {mode === 'pin' ? (
        <PinPad />
      ) : (
        <form onSubmit={submit} className="space-y-3">
          <Field label="Username">
            <input className="input" autoFocus value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </Field>
          <Field label="Password">
            <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          </Field>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button type="submit" size="lg" className="w-full" loading={busy}>
            Sign in
          </Button>
        </form>
      )}
    </Shell>
  )
}

export function LockScreen() {
  const logout = useAuth((s) => s.logout)
  return (
    <Shell title="Till locked – who is selling?">
      <PinPad />
      <button className="mt-4 w-full text-center text-sm text-slate-500 hover:text-slate-700" onClick={logout}>
        Sign in with password instead
      </button>
    </Shell>
  )
}
