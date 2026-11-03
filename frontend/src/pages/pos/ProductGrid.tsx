import { useMemo, useState } from 'react'
import type { PosItem } from '../../api/types'
import { Loading } from '../../components/ui'
import { money, qty, toNumber } from '../../lib/format'
import { useCategories, usePosItems } from '../../lib/hooks'

/** Category tabs + searchable tile grid. Used by the retail register and restaurant orders. */
export function ProductGrid({ onPick, search }: { onPick: (item: PosItem) => void; search: string }) {
  const items = usePosItems()
  const categories = useCategories()
  const [category, setCategory] = useState<number | 'all'>('all')

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase()
    return (items.data ?? []).filter((i) => {
      if (term) {
        return i.name.toLowerCase().includes(term) || i.sku?.toLowerCase() === term || i.barcodes.includes(term)
      }
      return category === 'all' || i.category === category
    })
  }, [items.data, search, category])

  if (items.isLoading) return <Loading />
  const cats = (categories.data ?? []).filter((c) => c.is_active)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex gap-2 overflow-x-auto px-3 pb-2">
        <CategoryChip active={category === 'all'} color="#334155" onClick={() => setCategory('all')}>
          All
        </CategoryChip>
        {cats.map((c) => (
          <CategoryChip key={c.id} active={category === c.id} color={c.color} onClick={() => setCategory(c.id)}>
            {c.name}
          </CategoryChip>
        ))}
      </div>
      <div className="grid flex-1 auto-rows-min grid-cols-2 gap-2 overflow-y-auto px-3 pb-3 sm:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
        {visible.map((item) => {
          const stock = toNumber(item.stock)
          const out = item.track_stock && stock <= 0
          return (
            <button
              key={item.id}
              onClick={() => onPick(item)}
              className="group relative flex min-h-[92px] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white text-left shadow-sm transition hover:border-brand-400 hover:shadow active:scale-[0.98]"
            >
              <span className="h-1.5 w-full" style={{ background: item.category_color ?? '#cbd5e1' }} />
              {item.image && <img src={item.image} alt="" className="h-20 w-full object-cover" />}
              <span className="flex flex-1 flex-col p-2">
                <span className="line-clamp-2 text-sm font-semibold leading-tight text-slate-800">{item.name}</span>
                <span className="mt-auto flex items-end justify-between pt-1">
                  <span className="text-sm font-bold text-brand-700">{money(item.price)}</span>
                  {item.track_stock && (
                    <span className={`text-[11px] font-semibold ${out ? 'text-red-600' : stock <= 5 ? 'text-amber-600' : 'text-slate-400'}`}>
                      {out ? 'Out' : qty(stock)}
                    </span>
                  )}
                </span>
              </span>
            </button>
          )
        })}
        {visible.length === 0 && <div className="col-span-full py-10 text-center text-sm text-slate-500">No products found.</div>}
      </div>
    </div>
  )
}

function CategoryChip({ active, color, onClick, children }: { active: boolean; color: string; onClick: () => void; children: string }) {
  return (
    <button
      onClick={onClick}
      className="whitespace-nowrap rounded-full border px-4 py-2 text-sm font-semibold transition"
      style={active ? { background: color, borderColor: color, color: 'white' } : { borderColor: '#e2e8f0', background: 'white' }}
    >
      {children}
    </button>
  )
}
