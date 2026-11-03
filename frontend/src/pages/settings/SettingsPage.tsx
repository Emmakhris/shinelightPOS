import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import type { BusinessSettings, FloorArea, Table, TaxRate } from '../../api/types'
import { toast } from '../../components/toast'
import { Button, Field, Loading, Modal, PageHeader, Tabs, Toggle } from '../../components/ui'
import { useSettings } from '../../lib/hooks'
import { useAuth } from '../../stores/auth'

type Tab = 'business' | 'selling' | 'receipt' | 'taxes' | 'tables'

export function SettingsPage() {
  const can = useAuth((s) => s.can)
  const owner = can('manage_settings')
  const [tab, setTab] = useState<Tab>(owner ? 'business' : 'tables')
  const tabs: { value: Tab; label: string }[] = [
    ...(owner
      ? [
          { value: 'business' as const, label: 'Business' },
          { value: 'selling' as const, label: 'Selling & loyalty' },
          { value: 'receipt' as const, label: 'Receipt' },
          { value: 'taxes' as const, label: 'Taxes' },
        ]
      : []),
    { value: 'tables', label: 'Tables' },
  ]
  return (
    <div>
      <PageHeader title="Settings" />
      <Tabs value={tab} onChange={setTab} tabs={tabs} />
      {tab === 'business' && <SettingsForm fields="business" />}
      {tab === 'selling' && <SettingsForm fields="selling" />}
      {tab === 'receipt' && <SettingsForm fields="receipt" />}
      {tab === 'taxes' && <Taxes />}
      {tab === 'tables' && <Tables />}
    </div>
  )
}

function SettingsForm({ fields }: { fields: 'business' | 'selling' | 'receipt' }) {
  const qc = useQueryClient()
  const settings = useSettings()
  const [s, setS] = useState<BusinessSettings | null>(null)
  const [busy, setBusy] = useState(false)
  const logoRef = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (settings.data) setS(settings.data)
  }, [settings.data])
  if (!s) return <Loading />
  const set = <K extends keyof BusinessSettings>(k: K, v: BusinessSettings[K]) => setS({ ...s, [k]: v })

  const save = async () => {
    setBusy(true)
    try {
      const { logo: _logo, setup_complete: _sc, ...body } = s
      void _logo
      void _sc
      await api.patch('/settings/', body)
      qc.invalidateQueries({ queryKey: ['settings'] })
      toast.success('Settings saved')
    } catch (err) {
      toast.error(err)
    } finally {
      setBusy(false)
    }
  }

  const uploadLogo = async (file: File) => {
    const form = new FormData()
    form.append('logo', file)
    try {
      await api.patch('/settings/', form)
      qc.invalidateQueries({ queryKey: ['settings'] })
    } catch (err) {
      toast.error(err)
    }
  }

  return (
    <div className="card max-w-3xl p-5">
      {fields === 'business' && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Business name"><input className="input" value={s.name} onChange={(e) => set('name', e.target.value)} /></Field>
          <Field label="Registered / legal name"><input className="input" value={s.legal_name} onChange={(e) => set('legal_name', e.target.value)} /></Field>
          <Field label="TIN / Ghana Card"><input className="input" value={s.tin} onChange={(e) => set('tin', e.target.value)} /></Field>
          <Field label="Phone"><input className="input" value={s.phone} onChange={(e) => set('phone', e.target.value)} /></Field>
          <Field label="Email"><input className="input" value={s.email} onChange={(e) => set('email', e.target.value)} /></Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Currency"><input className="input" value={s.currency_code} onChange={(e) => set('currency_code', e.target.value.toUpperCase().slice(0, 3))} /></Field>
            <Field label="Symbol"><input className="input" value={s.currency_symbol} onChange={(e) => set('currency_symbol', e.target.value)} /></Field>
          </div>
          <Field label="Address" className="sm:col-span-2"><textarea className="input" rows={2} value={s.address} onChange={(e) => set('address', e.target.value)} /></Field>
          <div className="sm:col-span-2">
            <Toggle checked={s.vat_registered} onChange={(v) => set('vat_registered', v)} label="VAT registered" hint="Receipts show 'TAX INVOICE'. Turn the tax rates on in the Taxes tab." />
          </div>
          <div className="flex items-center gap-3 sm:col-span-2">
            {s.logo && <img src={s.logo} alt="logo" className="h-14 rounded" />}
            <input ref={logoRef} type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && uploadLogo(e.target.files[0])} />
            <Button variant="secondary" size="sm" onClick={() => logoRef.current?.click()}>{s.logo ? 'Change logo' : 'Upload logo'}</Button>
          </div>
        </div>
      )}
      {fields === 'selling' && (
        <div className="space-y-2">
          <Toggle checked={s.retail_mode} onChange={(v) => set('retail_mode', v)} label="Retail register" />
          <Toggle checked={s.restaurant_mode} onChange={(v) => set('restaurant_mode', v)} label="Restaurant tables & kitchen tickets" />
          <Toggle checked={s.prices_include_tax} onChange={(v) => set('prices_include_tax', v)} label="Prices include tax" hint="Off: VAT and levies are added on top at the till." />
          <Toggle checked={s.require_open_shift} onChange={(v) => set('require_open_shift', v)} label="Cashiers must open a shift before taking payment" hint="Recommended: makes cash-up and over/short tracking possible." />
          <Toggle checked={s.allow_negative_stock} onChange={(v) => set('allow_negative_stock', v)} label="Allow selling when stock shows zero" />
          <Field label="Discounts above this % need a manager PIN" className="max-w-xs">
            <input className="input" type="number" min={0} max={100} value={s.discount_approval_percent} onChange={(e) => set('discount_approval_percent', e.target.value)} />
          </Field>
          <hr className="my-3" />
          <Toggle checked={s.loyalty_enabled} onChange={(v) => set('loyalty_enabled', v)} label="Loyalty points" />
          <div className="grid max-w-md grid-cols-2 gap-3">
            <Field label="Points per GH₵ 1 spent"><input className="input" value={s.loyalty_points_per_cedi} onChange={(e) => set('loyalty_points_per_cedi', e.target.value)} /></Field>
            <Field label="GH₵ value of 1 point"><input className="input" value={s.loyalty_point_value} onChange={(e) => set('loyalty_point_value', e.target.value)} /></Field>
          </div>
        </div>
      )}
      {fields === 'receipt' && (
        <div className="space-y-3">
          <Field label="Paper width">
            <select className="input max-w-xs" value={s.receipt_width} onChange={(e) => set('receipt_width', Number(e.target.value) as 80 | 58)}>
              <option value={80}>80 mm</option>
              <option value={58}>58 mm</option>
            </select>
          </Field>
          <Field label="Header text (under your address)"><textarea className="input" rows={2} value={s.receipt_header} onChange={(e) => set('receipt_header', e.target.value)} /></Field>
          <Field label="Footer text"><textarea className="input" rows={2} value={s.receipt_footer} onChange={(e) => set('receipt_footer', e.target.value)} /></Field>
          <Toggle checked={s.show_tax_on_receipt} onChange={(v) => set('show_tax_on_receipt', v)} label="Show tax breakdown on receipts" />
        </div>
      )}
      <Button className="mt-5" loading={busy} onClick={save}>Save changes</Button>
    </div>
  )
}

function Taxes() {
  const qc = useQueryClient()
  const taxes = useQuery({ queryKey: ['tax-rates'], queryFn: () => api.get<TaxRate[]>('/tax-rates/') })
  const [edit, setEdit] = useState<Partial<TaxRate> | null>(null)
  const save = async () => {
    if (!edit) return
    try {
      if (edit.id) await api.patch(`/tax-rates/${edit.id}/`, edit)
      else await api.post('/tax-rates/', edit)
      qc.invalidateQueries({ queryKey: ['tax-rates'] })
      setEdit(null)
    } catch (err) {
      toast.error(err)
    }
  }
  return (
    <div className="max-w-3xl">
      <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
        Ghana's VAT and levy rules have changed several times. The defaults are VAT 15%, NHIL 2.5% and GETFund 2.5%, each charged on the item value.
        Check the current rates, and whether any tax is charged on top of another ("compound"), with GRA or your accountant before you start selling.
      </div>
      <div className="card overflow-x-auto">
        <table className="table">
          <thead><tr><th>Order</th><th>Name</th><th>Code</th><th className="text-right">Rate</th><th>Compound</th><th>Active</th><th></th></tr></thead>
          <tbody>
            {taxes.data?.map((t) => (
              <tr key={t.id}>
                <td>{t.sort_order}</td><td className="font-semibold">{t.name}</td><td>{t.code}</td><td className="text-right">{Number(t.rate)}%</td>
                <td>{t.compound ? 'Yes' : 'No'}</td><td>{t.is_active ? 'On' : 'Off'}</td>
                <td className="text-right"><Button size="sm" variant="secondary" onClick={() => setEdit(t)}>Edit</Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Button className="mt-3" variant="secondary" onClick={() => setEdit({ name: '', code: '', rate: '0', compound: false, sort_order: (taxes.data?.length ?? 0) + 1, is_active: true })}>+ Add tax</Button>
      {edit && (
        <Modal open size="sm" onClose={() => setEdit(null)} title={edit.id ? `Edit ${edit.name}` : 'New tax'} footer={<Button onClick={save}>Save</Button>}>
          <div className="space-y-3">
            <Field label="Name"><input className="input" value={edit.name ?? ''} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
            <Field label="Code"><input className="input" value={edit.code ?? ''} onChange={(e) => setEdit({ ...edit, code: e.target.value.toUpperCase() })} /></Field>
            <Field label="Rate %"><input className="input" inputMode="decimal" value={edit.rate ?? ''} onChange={(e) => setEdit({ ...edit, rate: e.target.value })} /></Field>
            <Field label="Order (taxes apply in this order)"><input className="input" type="number" value={edit.sort_order ?? 0} onChange={(e) => setEdit({ ...edit, sort_order: Number(e.target.value) })} /></Field>
            <Toggle checked={!!edit.compound} onChange={(v) => setEdit({ ...edit, compound: v })} label="Compound" hint="Charged on the value plus the taxes before it." />
            <Toggle checked={!!edit.is_active} onChange={(v) => setEdit({ ...edit, is_active: v })} label="Active" />
          </div>
        </Modal>
      )}
    </div>
  )
}

function Tables() {
  const qc = useQueryClient()
  const areas = useQuery({ queryKey: ['areas'], queryFn: () => api.get<FloorArea[]>('/restaurant/areas/') })
  const tables = useQuery({ queryKey: ['tables'], queryFn: () => api.get<Table[]>('/restaurant/tables/') })
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['areas'] })
    qc.invalidateQueries({ queryKey: ['tables'] })
    qc.invalidateQueries({ queryKey: ['floor'] })
  }
  const run = async (fn: () => Promise<unknown>) => {
    try {
      await fn()
      refresh()
    } catch (err) {
      toast.error(err)
    }
  }
  const addArea = () => {
    const name = window.prompt('Area name, e.g. Main Hall, Terrace, Bar')
    if (name) run(() => api.post('/restaurant/areas/', { name, sort_order: areas.data?.length ?? 0 }))
  }
  const addTables = (area: FloorArea) => {
    const input = window.prompt('Table names, separated by commas (e.g. T1, T2, T3)')
    if (!input) return
    const names = input.split(',').map((s) => s.trim()).filter(Boolean)
    run(() => Promise.all(names.map((name, i) => api.post('/restaurant/tables/', { area: area.id, name, seats: 4, sort_order: i }))))
  }
  return (
    <div className="max-w-3xl space-y-3">
      {areas.data?.map((a) => (
        <div key={a.id} className="card p-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="font-bold">{a.name}</h3>
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" onClick={() => addTables(a)}>+ Tables</Button>
              <Button size="sm" variant="ghost" onClick={() => window.confirm(`Delete ${a.name} and its tables?`) && run(() => api.del(`/restaurant/areas/${a.id}/`))}>Delete area</Button>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {tables.data?.filter((t) => t.area === a.id).map((t) => (
              <span key={t.id} className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm ${t.is_active ? '' : 'opacity-50'}`}>
                <b>{t.name}</b>
                <input
                  className="w-12 rounded border px-1 text-xs"
                  type="number"
                  title="Seats"
                  defaultValue={t.seats}
                  onBlur={(e) => Number(e.target.value) !== t.seats && run(() => api.patch(`/restaurant/tables/${t.id}/`, { seats: Number(e.target.value) }))}
                />
                <button className="text-xs text-slate-500" onClick={() => run(() => api.patch(`/restaurant/tables/${t.id}/`, { is_active: !t.is_active }))}>
                  {t.is_active ? 'hide' : 'show'}
                </button>
              </span>
            ))}
          </div>
        </div>
      ))}
      <Button onClick={addArea}>+ Add area</Button>
    </div>
  )
}
