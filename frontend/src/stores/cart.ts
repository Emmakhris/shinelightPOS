import { create } from 'zustand'
import type { Customer, PosItem } from '../api/types'
import { round2, toNumber } from '../lib/format'

export type DiscountType = 'amount' | 'percent'

export interface CartModifier {
  id: number
  name: string
  price: string
}

export interface CartLine {
  key: string
  item: PosItem
  quantity: number
  modifiers: CartModifier[]
  discountType: DiscountType
  discountValue: number
  /** Manager-approved price change; undefined means the list price. */
  unitPrice?: number
  note: string
}

export interface CartSnapshot {
  lines: CartLine[]
  customer: Customer | null
  discountType: DiscountType
  discountValue: number
  note: string
}

interface CartState extends CartSnapshot {
  add: (item: PosItem, modifiers?: CartModifier[], quantity?: number) => void
  update: (key: string, patch: Partial<Omit<CartLine, 'key' | 'item'>>) => void
  remove: (key: string) => void
  setCustomer: (customer: Customer | null) => void
  setDiscount: (type: DiscountType, value: number) => void
  setNote: (note: string) => void
  clear: () => void
  load: (snapshot: CartSnapshot) => void
}

const empty: CartSnapshot = { lines: [], customer: null, discountType: 'amount', discountValue: 0, note: '' }

function lineKey(itemId: number, modifiers: CartModifier[]) {
  return `${itemId}:${modifiers.map((m) => m.id).sort((a, b) => a - b).join(',')}`
}

// ---- Pure helpers (unit tested). The server recalculates everything at checkout. ----

export function unitPrice(line: CartLine): number {
  if (line.unitPrice !== undefined) return line.unitPrice
  return round2(toNumber(line.item.price) + line.modifiers.reduce((s, m) => s + toNumber(m.price), 0))
}

export function lineGross(line: CartLine): number {
  return round2(unitPrice(line) * line.quantity)
}

export function lineDiscount(line: CartLine): number {
  const gross = lineGross(line)
  if (line.discountType === 'percent') return round2((gross * Math.min(Math.max(line.discountValue, 0), 100)) / 100)
  return round2(Math.min(Math.max(line.discountValue, 0), gross))
}

export function lineTotal(line: CartLine): number {
  return round2(lineGross(line) - lineDiscount(line))
}

export function cartDiscount(snapshot: Pick<CartSnapshot, 'lines' | 'discountType' | 'discountValue'>): number {
  const afterLines = snapshot.lines.reduce((s, l) => s + lineTotal(l), 0)
  if (snapshot.discountType === 'percent') {
    return round2((afterLines * Math.min(Math.max(snapshot.discountValue, 0), 100)) / 100)
  }
  return round2(Math.min(Math.max(snapshot.discountValue, 0), afterLines))
}

/** Total when prices include tax (the default). With tax-exclusive pricing, the server quote adds tax. */
export function cartTotal(snapshot: Pick<CartSnapshot, 'lines' | 'discountType' | 'discountValue'>): number {
  return round2(snapshot.lines.reduce((s, l) => s + lineTotal(l), 0) - cartDiscount(snapshot))
}

/** What /sales/quote/ and /sales/checkout/ expect. */
export function toApiLines(lines: CartLine[]) {
  return lines.map((l) => ({
    variant: l.item.id,
    quantity: String(l.quantity),
    modifiers: l.modifiers.map((m) => m.id),
    discount_type: l.discountType,
    discount_value: String(l.discountValue || 0),
    unit_price: l.unitPrice === undefined ? null : String(l.unitPrice),
    note: l.note,
  }))
}

export const useCart = create<CartState>((set) => ({
  ...empty,

  add(item, modifiers = [], quantity = 1) {
    set((state) => {
      const key = lineKey(item.id, modifiers)
      const existing = state.lines.find((l) => l.key === key)
      if (existing) {
        return {
          lines: state.lines.map((l) => (l.key === key ? { ...l, quantity: round3(l.quantity + quantity) } : l)),
        }
      }
      const line: CartLine = { key, item, quantity, modifiers, discountType: 'amount', discountValue: 0, note: '' }
      return { lines: [...state.lines, line] }
    })
  },

  update(key, patch) {
    set((state) => ({ lines: state.lines.map((l) => (l.key === key ? { ...l, ...patch } : l)) }))
  },

  remove(key) {
    set((state) => ({ lines: state.lines.filter((l) => l.key !== key) }))
  },

  setCustomer: (customer) => set({ customer }),
  setDiscount: (discountType, discountValue) => set({ discountType, discountValue }),
  setNote: (note) => set({ note }),
  clear: () => set({ ...empty }),
  load: (snapshot) => set({ ...empty, ...snapshot }),
}))

function round3(n: number) {
  return Math.round(n * 1000) / 1000
}
