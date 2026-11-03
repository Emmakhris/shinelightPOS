import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { api, downloadCsv, qs } from '../../api/client'
import type { Category, ModifierGroup, Product, TaxCategory, Variant } from '../../api/types'
import { toast } from '../../components/toast'
import { Badge, Button, Empty, Field, Loading, Modal, PageHeader, Tabs, Toggle } from '../../components/ui'
import { money, qty, toNumber } from '../../lib/format'
import { useModifierGroups } from '../../lib/hooks'

const UNITS = [
  ['pc', 'Piece'], ['kg', 'Kilogram'], ['g', 'Gram'], ['l', 'Litre'], ['ml', 'Millilitre'],
  ['m', 'Metre'], ['pack', 'Pack'], ['box', 'Box'], ['plate', 'Plate'],
]
const TAX_LABELS: Record<TaxCategory, string> = { standard: 'Standard (VAT + levies)', zero: 'Zero rated', exempt: 'Exempt' }

type Tab = 'products' | 'categories' | 'modifiers'

export function ProductsPage() {
  const [tab, setTab] = useState<Tab>('products')
  return (
    <div>
      <PageHeader title="Products" subtitle="Your catalogue, prices, barcodes and options." />
      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: 'products', label: 'Products' },
          { value: 'categories', label: 'Categories' },
          { value: 'modifiers', label: 'Options / modifiers' },
        ]}
      />
      {tab === 'products' && <ProductList />}
      {tab === 'categories' && <Categories />}
      {tab === 'modifiers' && <ModifierGroups />}
    </div>
  )
}

function useCats() {
  return useQuery({ queryKey: ['categories'], queryFn: () => api.get<Category[]>('/catalog/categories/') })
}

function ProductList() {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [editing, setEditing] = useState<Product | 'new' | null>(null)
  const [importing, setImporting] = useState(false)
  const cats = useCats()
  const products = useQuery({
    queryKey: ['products', search, category, showArchived],
    queryFn: () => api.get<Product[]>(`/catalog/products/${qs({ search, category, is_active: !showArchived })}`),
  })

  return (
    <>
      <div className="mb-3 flex flex-wrap gap-2">
        <input className="input max-w-xs" placeholder="Search name, SKU or barcode" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className="input max-w-[200px]" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">All categories</option>
          {cats.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <Toggle checked={showArchived} onChange={setShowArchived} label="Show archived" />
        <div className="ml-auto flex gap-2">
          <Button variant="secondary" onClick={() => downloadCsv('/catalog/products/export/', 'products.csv').catch(toast.error)}>Export CSV</Button>
          <Button variant="secondary" onClick={() => setImporting(true)}>Import CSV</Button>
          <Button onClick={() => setEditing('new')}>+ New product</Button>
        </div>
      </div>
      <div className="card overflow-x-auto">
        {products.isLoading ? <Loading /> : (
          <table className="table">
            <thead><tr><th></th><th>Name</th><th>Category</th><th>SKU / barcode</th><th className="text-right">Price</th><th className="text-right">Cost</th><th className="text-right">Stock</th><th>Tax</th></tr></thead>
            <tbody>
              {products.data?.map((p) => {
                const v = p.variants[0]
                const stock = p.variants.reduce((s, x) => s + toNumber(x.stock), 0)
                const low = p.track_stock && stock <= toNumber(p.low_stock_threshold)
                return (
                  <tr key={p.id} className="cursor-pointer" onClick={() => setEditing(p)}>
                    <td className="w-12">{p.image ? <img src={p.image} className="h-9 w-9 rounded object-cover" alt="" /> : <div className="h-9 w-9 rounded bg-slate-100" />}</td>
                    <td className="font-semibold">
                      {p.name}
                      {p.has_variants && <span className="ml-2 text-xs font-normal text-slate-500">{p.variants.length} variants</span>}
                      {!p.is_active && <Badge color="red">Archived</Badge>}
                    </td>
                    <td>{p.category_name ?? '—'}</td>
                    <td className="font-mono text-xs">{v?.sku}{v?.barcodes.length ? ` · ${v.barcodes.join(', ')}` : ''}</td>
                    <td className="text-right">{p.has_variants ? 'various' : money(v?.price)}</td>
                    <td className="text-right text-slate-500">{p.has_variants ? '' : money(v?.cost_price)}</td>
                    <td className={`text-right ${low ? 'font-semibold text-red-600' : ''}`}>{p.track_stock ? `${qty(stock)} ${p.unit}` : '—'}</td>
                    <td><Badge color={p.tax_category === 'standard' ? 'blue' : 'gray'}>{p.tax_category}</Badge></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
        {products.data?.length === 0 && <Empty>No products yet.</Empty>}
      </div>
      {editing && <ProductForm product={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
      {importing && <ImportModal onClose={() => setImporting(false)} />}
    </>
  )
}

const blankVariant = (): Variant => ({ name: '', sku: '', price: '', cost_price: '', is_active: true, sort_order: 0, barcodes: [], opening_stock: '' })

function ProductForm({ product, onClose }: { product: Product | null; onClose: () => void }) {
  const qc = useQueryClient()
  const cats = useCats()
  const groups = useModifierGroups()
  const fileRef = useRef<HTMLInputElement>(null)
  const [p, setP] = useState(() => ({
    name: product?.name ?? '',
    category: product?.category ?? null,
    description: product?.description ?? '',
    unit: product?.unit ?? 'pc',
    tax_category: product?.tax_category ?? ('standard' as TaxCategory),
    track_stock: product?.track_stock ?? true,
    low_stock_threshold: product?.low_stock_threshold ?? '5',
    has_variants: product?.has_variants ?? false,
    is_kitchen_item: product?.is_kitchen_item ?? false,
    modifier_groups: product?.modifier_groups ?? [],
    is_active: product?.is_active ?? true,
  }))
  const [variants, setVariants] = useState<Variant[]>(product?.variants.length ? product.variants : [blankVariant()])
  const set = <K extends keyof typeof p>(k: K, v: (typeof p)[K]) => setP((prev) => ({ ...prev, [k]: v }))
  const setVar = (i: number, patch: Partial<Variant>) => setVariants((vs) => vs.map((v, j) => (i === j ? { ...v, ...patch } : v)))

  const save = useMutation({
    mutationFn: () => {
      const body = {
        ...p,
        variants: (p.has_variants ? variants : variants.slice(0, 1)).map((v, i) => ({
          ...(v.id ? { id: v.id } : {}),
          name: p.has_variants ? v.name : '',
          sku: v.sku || null,
          price: v.price || '0',
          cost_price: v.cost_price || '0',
          is_active: true,
          sort_order: i,
          barcodes: v.barcodes.filter(Boolean),
          ...(!v.id && v.opening_stock ? { opening_stock: v.opening_stock } : {}),
        })),
      }
      return product ? api.put<Product>(`/catalog/products/${product.id}/`, body) : api.post<Product>('/catalog/products/', body)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['products'] })
      qc.invalidateQueries({ queryKey: ['pos-items'] })
      toast.success('Product saved')
      onClose()
    },
    onError: (e) => toast.error(e),
  })

  const archive = async () => {
    if (!product || !window.confirm(`Archive ${product.name}? It will disappear from the till.`)) return
    await api.del(`/catalog/products/${product.id}/`)
    qc.invalidateQueries({ queryKey: ['products'] })
    qc.invalidateQueries({ queryKey: ['pos-items'] })
    onClose()
  }

  const uploadImage = async (file: File) => {
    if (!product) return
    const form = new FormData()
    form.append('image', file)
    try {
      await api.post(`/catalog/products/${product.id}/image/`, form)
      qc.invalidateQueries({ queryKey: ['products'] })
      qc.invalidateQueries({ queryKey: ['pos-items'] })
      toast.success('Image uploaded')
    } catch (err) {
      toast.error(err)
    }
  }

  return (
    <Modal
      open
      size="lg"
      onClose={onClose}
      title={product ? `Edit ${product.name}` : 'New product'}
      footer={
        <>
          {product?.is_active && <Button variant="danger" className="mr-auto" onClick={archive}>Archive</Button>}
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button loading={save.isPending} disabled={!p.name} onClick={() => save.mutate()}>Save</Button>
        </>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name" className="sm:col-span-2">
          <input className="input" autoFocus value={p.name} onChange={(e) => set('name', e.target.value)} />
        </Field>
        <Field label="Category">
          <select className="input" value={p.category ?? ''} onChange={(e) => set('category', e.target.value ? Number(e.target.value) : null)}>
            <option value="">None</option>
            {cats.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </Field>
        <Field label="Sold by">
          <select className="input" value={p.unit} onChange={(e) => set('unit', e.target.value)}>
            {UNITS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Field>
        <Field label="Tax">
          <select className="input" value={p.tax_category} onChange={(e) => set('tax_category', e.target.value as TaxCategory)}>
            {Object.entries(TAX_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Field>
        <Field label="Low stock alert at">
          <input className="input" type="number" min={0} value={p.low_stock_threshold} onChange={(e) => set('low_stock_threshold', e.target.value)} disabled={!p.track_stock} />
        </Field>
      </div>
      <div className="mt-3 grid gap-1 sm:grid-cols-2">
        <Toggle checked={p.track_stock} onChange={(v) => set('track_stock', v)} label="Track stock" hint="Turn off for services and cooked food." />
        <Toggle checked={p.is_kitchen_item} onChange={(v) => set('is_kitchen_item', v)} label="Send to kitchen" hint="Prints on kitchen tickets." />
        <Toggle checked={p.has_variants} onChange={(v) => set('has_variants', v)} label="Has variants" hint="e.g. sizes or colours with their own price and stock." />
        {!p.is_active && <Toggle checked={p.is_active} onChange={(v) => set('is_active', v)} label="Active (restore)" />}
      </div>

      <h3 className="mb-2 mt-4 text-sm font-bold">{p.has_variants ? 'Variants' : 'Price & codes'}</h3>
      <div className="space-y-2">
        {(p.has_variants ? variants : variants.slice(0, 1)).map((v, i) => (
          <div key={v.id ?? `new-${i}`} className="grid gap-2 rounded-lg border border-slate-200 p-2 sm:grid-cols-6">
            {p.has_variants && <input className="input sm:col-span-2" placeholder="Variant name e.g. Large" value={v.name} onChange={(e) => setVar(i, { name: e.target.value })} />}
            <input className="input" placeholder="Price" inputMode="decimal" value={v.price} onChange={(e) => setVar(i, { price: e.target.value })} />
            <input className="input" placeholder="Cost" inputMode="decimal" value={v.cost_price} onChange={(e) => setVar(i, { cost_price: e.target.value })} />
            <input className="input" placeholder="SKU" value={v.sku ?? ''} onChange={(e) => setVar(i, { sku: e.target.value })} />
            <input
              className={`input ${p.has_variants ? 'sm:col-span-2' : 'sm:col-span-2'}`}
              placeholder="Barcodes (comma separated)"
              value={v.barcodes.join(', ')}
              onChange={(e) => setVar(i, { barcodes: e.target.value.split(',').map((s) => s.trim()) })}
            />
            {!v.id && p.track_stock && (
              <input className="input" placeholder="Opening stock" inputMode="decimal" value={v.opening_stock ?? ''} onChange={(e) => setVar(i, { opening_stock: e.target.value })} />
            )}
            {v.id && p.track_stock && <div className="flex items-center text-xs text-slate-500">In stock: {qty(v.stock)}</div>}
            {p.has_variants && variants.length > 1 && (
              <Button variant="ghost" size="sm" onClick={() => setVariants(variants.filter((_, j) => j !== i))}>Remove</Button>
            )}
          </div>
        ))}
        {p.has_variants && <Button variant="secondary" size="sm" onClick={() => setVariants([...variants, blankVariant()])}>+ Add variant</Button>}
      </div>

      {(groups.data?.length ?? 0) > 0 && (
        <>
          <h3 className="mb-2 mt-4 text-sm font-bold">Options offered at the till</h3>
          <div className="flex flex-wrap gap-2">
            {groups.data?.map((g) => {
              const on = p.modifier_groups.includes(g.id)
              return (
                <button
                  key={g.id}
                  onClick={() => set('modifier_groups', on ? p.modifier_groups.filter((x) => x !== g.id) : [...p.modifier_groups, g.id])}
                  className={`rounded-full border px-3 py-1 text-sm ${on ? 'border-brand-500 bg-brand-50 text-brand-800' : 'border-slate-300'}`}
                >
                  {g.name}
                </button>
              )
            })}
          </div>
        </>
      )}

      {product && (
        <div className="mt-4 flex items-center gap-3">
          {product.image && <img src={product.image} alt="" className="h-16 w-16 rounded object-cover" />}
          <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && uploadImage(e.target.files[0])} />
          <Button variant="secondary" size="sm" onClick={() => fileRef.current?.click()}>{product.image ? 'Change image' : 'Add image'}</Button>
        </div>
      )}
    </Modal>
  )
}

function ImportModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<{ created: number; updated: number; errors: string[] } | null>(null)
  const [busy, setBusy] = useState(false)
  const run = async () => {
    if (!file) return
    setBusy(true)
    const form = new FormData()
    form.append('file', file)
    try {
      setResult(await api.post('/catalog/products/import/', form))
      qc.invalidateQueries({ queryKey: ['products'] })
      qc.invalidateQueries({ queryKey: ['pos-items'] })
    } catch (err) {
      toast.error(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open onClose={onClose} title="Import products from CSV">
      <p className="mb-2 text-sm text-slate-600">
        Columns: <code className="text-xs">name, sku, barcodes, category, unit, price, cost_price, tax_category, track_stock, stock, low_stock_threshold</code>.
        Separate several barcodes with <code>|</code>. Rows with an existing SKU update its price and cost.
      </p>
      <p className="mb-3 text-sm text-slate-600">Tip: export first to get a file in the right format.</p>
      <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="mb-3 block text-sm" />
      <Button loading={busy} disabled={!file} onClick={run}>Import</Button>
      {result && (
        <div className="mt-4 rounded-lg bg-slate-50 p-3 text-sm">
          <p>Created {result.created}, updated {result.updated}.</p>
          {result.errors.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-red-600">
              {result.errors.slice(0, 20).map((e) => <li key={e}>{e}</li>)}
            </ul>
          )}
        </div>
      )}
    </Modal>
  )
}

function Categories() {
  const qc = useQueryClient()
  const cats = useCats()
  const [edit, setEdit] = useState<Partial<Category> | null>(null)
  const save = async () => {
    if (!edit) return
    try {
      if (edit.id) await api.patch(`/catalog/categories/${edit.id}/`, edit)
      else await api.post('/catalog/categories/', edit)
      qc.invalidateQueries({ queryKey: ['categories'] })
      setEdit(null)
    } catch (err) {
      toast.error(err)
    }
  }
  return (
    <>
      <div className="mb-3 flex justify-end"><Button onClick={() => setEdit({ name: '', color: '#2563eb', sort_order: 0, is_active: true })}>+ New category</Button></div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {cats.data?.map((c) => (
          <button key={c.id} onClick={() => setEdit(c)} className="card flex items-center gap-3 p-3 text-left hover:border-brand-400">
            <span className="h-8 w-8 rounded-full" style={{ background: c.color }} />
            <span>
              <span className="font-semibold">{c.name}</span>
              <span className="block text-xs text-slate-500">{c.product_count} products{!c.is_active && ' · hidden'}</span>
            </span>
          </button>
        ))}
      </div>
      {edit && (
        <Modal open size="sm" onClose={() => setEdit(null)} title={edit.id ? 'Edit category' : 'New category'} footer={<Button onClick={save} disabled={!edit.name}>Save</Button>}>
          <div className="space-y-3">
            <Field label="Name"><input className="input" autoFocus value={edit.name ?? ''} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
            <Field label="Colour"><input type="color" className="h-10 w-20" value={edit.color} onChange={(e) => setEdit({ ...edit, color: e.target.value })} /></Field>
            <Field label="Order on till"><input type="number" className="input" value={edit.sort_order ?? 0} onChange={(e) => setEdit({ ...edit, sort_order: Number(e.target.value) })} /></Field>
            <Toggle checked={!!edit.is_active} onChange={(v) => setEdit({ ...edit, is_active: v })} label="Show on till" />
          </div>
        </Modal>
      )}
    </>
  )
}

function ModifierGroups() {
  const qc = useQueryClient()
  const groups = useModifierGroups()
  const [edit, setEdit] = useState<Partial<ModifierGroup> | null>(null)
  const save = async () => {
    if (!edit) return
    try {
      if (edit.id) await api.put(`/catalog/modifier-groups/${edit.id}/`, edit)
      else await api.post('/catalog/modifier-groups/', edit)
      qc.invalidateQueries({ queryKey: ['modifier-groups'] })
      setEdit(null)
    } catch (err) {
      toast.error(err)
    }
  }
  const mods = edit?.modifiers ?? []
  return (
    <>
      <p className="mb-3 text-sm text-slate-600">Options the cashier picks when adding an item, e.g. "Protein: Chicken +15, Fish +20". Attach groups to products in the product form.</p>
      <div className="mb-3 flex justify-end"><Button onClick={() => setEdit({ name: '', min_select: 0, max_select: 0, sort_order: 0, modifiers: [] })}>+ New group</Button></div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {groups.data?.map((g) => (
          <button key={g.id} onClick={() => setEdit(g)} className="card p-3 text-left hover:border-brand-400">
            <div className="font-semibold">{g.name}</div>
            <div className="text-xs text-slate-500">{g.modifiers.map((m) => `${m.name}${toNumber(m.price) ? ` +${m.price}` : ''}`).join(', ')}</div>
          </button>
        ))}
      </div>
      {edit && (
        <Modal open onClose={() => setEdit(null)} title={edit.id ? 'Edit option group' : 'New option group'} footer={<Button onClick={save} disabled={!edit.name}>Save</Button>}>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Group name" className="sm:col-span-3"><input className="input" value={edit.name ?? ''} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
            <Field label="Must choose at least"><input type="number" min={0} className="input" value={edit.min_select ?? 0} onChange={(e) => setEdit({ ...edit, min_select: Number(e.target.value) })} /></Field>
            <Field label="Can choose at most" hint="0 = any number"><input type="number" min={0} className="input" value={edit.max_select ?? 0} onChange={(e) => setEdit({ ...edit, max_select: Number(e.target.value) })} /></Field>
          </div>
          <h3 className="mb-2 mt-4 text-sm font-bold">Options</h3>
          {mods.map((m, i) => (
            <div key={m.id ?? `n${i}`} className="mb-2 flex gap-2">
              <input className="input" placeholder="Name" value={m.name} onChange={(e) => setEdit({ ...edit, modifiers: mods.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)) })} />
              <input className="input w-32" placeholder="+ price" inputMode="decimal" value={m.price} onChange={(e) => setEdit({ ...edit, modifiers: mods.map((x, j) => (j === i ? { ...x, price: e.target.value } : x)) })} />
              <Button variant="ghost" onClick={() => setEdit({ ...edit, modifiers: mods.filter((_, j) => j !== i) })}>✕</Button>
            </div>
          ))}
          <Button variant="secondary" size="sm" onClick={() => setEdit({ ...edit, modifiers: [...mods, { name: '', price: '0', is_active: true, sort_order: mods.length }] })}>+ Add option</Button>
        </Modal>
      )}
    </>
  )
}
