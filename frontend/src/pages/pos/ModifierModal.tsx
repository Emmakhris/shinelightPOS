import { useState } from 'react'
import type { PosItem } from '../../api/types'
import { Button, Field, Modal } from '../../components/ui'
import { money, toNumber } from '../../lib/format'
import { useModifierGroups } from '../../lib/hooks'
import type { CartModifier } from '../../stores/cart'

export function ModifierModal({ item, onClose, onConfirm }: {
  item: PosItem
  onClose: () => void
  onConfirm: (modifiers: CartModifier[], quantity: number, note: string) => void
}) {
  const groups = (useModifierGroups().data ?? []).filter((g) => item.modifier_groups.includes(g.id))
  const [chosen, setChosen] = useState<CartModifier[]>([])
  const [quantity, setQuantity] = useState(1)
  const [note, setNote] = useState('')

  const toggle = (groupId: number, max: number, mod: CartModifier) => {
    setChosen((prev) => {
      if (prev.some((m) => m.id === mod.id)) return prev.filter((m) => m.id !== mod.id)
      const group = groups.find((g) => g.id === groupId)
      const inGroup = prev.filter((m) => group?.modifiers.some((gm) => gm.id === m.id))
      if (max === 1) return [...prev.filter((m) => !inGroup.includes(m)), mod]
      if (max && inGroup.length >= max) return prev
      return [...prev, mod]
    })
  }

  const missing = groups.filter((g) => chosen.filter((m) => g.modifiers.some((gm) => gm.id === m.id)).length < g.min_select)
  const unit = toNumber(item.price) + chosen.reduce((s, m) => s + toNumber(m.price), 0)

  return (
    <Modal
      open
      onClose={onClose}
      title={item.name}
      footer={
        <>
          <div className="mr-auto flex items-center gap-2">
            <Button variant="secondary" onClick={() => setQuantity(Math.max(1, quantity - 1))}>−</Button>
            <span className="w-8 text-center text-lg font-bold">{quantity}</span>
            <Button variant="secondary" onClick={() => setQuantity(quantity + 1)}>+</Button>
          </div>
          <Button size="lg" disabled={missing.length > 0} onClick={() => onConfirm(chosen, quantity, note)}>
            Add {money(unit * quantity)}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {groups.map((g) => (
          <div key={g.id}>
            <div className="mb-2 text-sm font-bold">
              {g.name}{' '}
              <span className="font-normal text-slate-500">
                {g.min_select ? `(choose ${g.max_select === 1 ? 'one' : `at least ${g.min_select}`})` : g.max_select === 1 ? '(optional, one)' : g.max_select ? `(optional, up to ${g.max_select})` : '(optional)'}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {g.modifiers.filter((m) => m.is_active).map((m) => {
                const on = chosen.some((c) => c.id === m.id)
                return (
                  <button
                    key={m.id}
                    onClick={() => toggle(g.id, g.max_select, { id: m.id!, name: m.name, price: m.price })}
                    className={`rounded-lg border p-3 text-left text-sm font-medium transition ${on ? 'border-brand-500 bg-brand-50 text-brand-800' : 'border-slate-200 hover:bg-slate-50'}`}
                  >
                    {m.name}
                    {toNumber(m.price) > 0 && <span className="block text-xs text-slate-500">+{money(m.price)}</span>}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
        <Field label="Note for kitchen">
          <input className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. no pepper" />
        </Field>
      </div>
    </Modal>
  )
}
