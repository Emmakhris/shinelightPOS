import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { Button, Field, Toggle } from '../components/ui'
import { useAuth } from '../stores/auth'

export function SetupPage() {
  const qc = useQueryClient()
  const login = useAuth((s) => s.login)
  const [step, setStep] = useState(1)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [f, setF] = useState({
    business_name: '', phone: '', email: '', address: '', tin: '', vat_registered: false,
    retail_mode: true, restaurant_mode: false, prices_include_tax: true,
    owner_first_name: '', owner_last_name: '', owner_username: '', owner_password: '', owner_pin: '',
    demo_data: true,
  })
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((prev) => ({ ...prev, [k]: v }))

  const finish = async () => {
    setBusy(true)
    setError('')
    try {
      await api.post('/setup/', f)
      await login(f.owner_username, f.owner_password)
      await qc.invalidateQueries({ queryKey: ['setup-status'] })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Setup failed')
    } finally {
      setBusy(false)
    }
  }

  const step1ok = f.business_name.trim() && (f.retail_mode || f.restaurant_mode)
  const step2ok = f.owner_first_name && f.owner_username && f.owner_password.length >= 6 && /^\d{4,6}$/.test(f.owner_pin)

  return (
    <div className="flex min-h-full items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-brand-900 p-4">
      <div className="w-full max-w-xl rounded-2xl bg-white p-6 shadow-2xl">
        <h1 className="text-2xl font-bold">Welcome to ShineLight POS</h1>
        <p className="mb-5 text-sm text-slate-500">Step {step} of 2 · Let's set up your business.</p>

        {step === 1 && (
          <div className="space-y-3">
            <Field label="Business name">
              <input className="input" autoFocus value={f.business_name} onChange={(e) => set('business_name', e.target.value)} />
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Phone">
                <input className="input" value={f.phone} onChange={(e) => set('phone', e.target.value)} />
              </Field>
              <Field label="TIN / Ghana Card">
                <input className="input" value={f.tin} onChange={(e) => set('tin', e.target.value)} />
              </Field>
            </div>
            <Field label="Business email" hint="Optional. Needed for MoMo prompts through Paystack, which emails payment receipts to it.">
              <input className="input" type="email" value={f.email} onChange={(e) => set('email', e.target.value.trim())} />
            </Field>
            <Field label="Address">
              <textarea className="input" rows={2} value={f.address} onChange={(e) => set('address', e.target.value)} />
            </Field>
            <div className="rounded-lg bg-slate-50 p-3">
              <Toggle checked={f.retail_mode} onChange={(v) => set('retail_mode', v)} label="Retail shop" hint="Barcode scanning, stock, quick checkout." />
              <Toggle checked={f.restaurant_mode} onChange={(v) => set('restaurant_mode', v)} label="Restaurant / bar" hint="Tables, kitchen tickets, open bills." />
              <Toggle
                checked={f.vat_registered}
                onChange={(v) => set('vat_registered', v)}
                label="VAT registered with GRA"
                hint="Turns on VAT 15%, NHIL 2.5% and GETFund 2.5%. Check the current rates with GRA; you can change them later in Settings."
              />
              <Toggle checked={f.prices_include_tax} onChange={(v) => set('prices_include_tax', v)} label="My prices already include tax" />
            </div>
            <Button className="w-full" size="lg" disabled={!step1ok} onClick={() => setStep(2)}>
              Next
            </Button>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-3">
            <p className="text-sm text-slate-600">Create the owner account. The PIN is for quick sign-in at the till and approving refunds and discounts.</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="First name">
                <input className="input" autoFocus value={f.owner_first_name} onChange={(e) => set('owner_first_name', e.target.value)} />
              </Field>
              <Field label="Last name">
                <input className="input" value={f.owner_last_name} onChange={(e) => set('owner_last_name', e.target.value)} />
              </Field>
              <Field label="Username">
                <input className="input" value={f.owner_username} onChange={(e) => set('owner_username', e.target.value.trim())} autoComplete="username" />
              </Field>
              <Field label="Password" hint="At least 6 characters">
                <input className="input" type="password" value={f.owner_password} onChange={(e) => set('owner_password', e.target.value)} autoComplete="new-password" />
              </Field>
              <Field label="PIN" hint="4 to 6 digits">
                <input className="input" inputMode="numeric" value={f.owner_pin} onChange={(e) => set('owner_pin', e.target.value.replace(/\D/g, '').slice(0, 6))} />
              </Field>
            </div>
            <Toggle checked={f.demo_data} onChange={(v) => set('demo_data', v)} label="Add sample products and tables" hint="Handy for training. You can archive them later." />
            {error && <p className="text-sm text-red-600">{error}</p>}
            <div className="flex gap-2">
              <Button variant="secondary" size="lg" onClick={() => setStep(1)}>
                Back
              </Button>
              <Button className="flex-1" size="lg" disabled={!step2ok} loading={busy} onClick={finish}>
                Finish setup
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
