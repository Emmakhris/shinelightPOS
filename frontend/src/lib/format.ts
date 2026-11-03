let currencySymbol = 'GH₵'

export function setCurrencySymbol(symbol: string) {
  currencySymbol = symbol || 'GH₵'
}

export function toNumber(value: string | number | null | undefined): number {
  if (value === null || value === undefined || value === '') return 0
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? n : 0
}

/** Round to pesewas, half away from zero, like the server does. */
export function round2(n: number): number {
  return Math.sign(n) * Math.round((Math.abs(n) + Number.EPSILON) * 100) / 100
}

export function money(value: string | number | null | undefined, withSymbol = true): string {
  const n = toNumber(value)
  const text = n.toLocaleString('en-GH', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return withSymbol ? `${currencySymbol} ${text}` : text
}

export function qty(value: string | number | null | undefined): string {
  const n = toNumber(value)
  return Number.isInteger(n) ? String(n) : n.toFixed(3).replace(/0+$/, '').replace(/\.$/, '')
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return ''
  return new Date(value).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export function time(value: string | null | undefined): string {
  if (!value) return ''
  return new Date(value).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}

export function isoDate(d: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export const METHOD_LABELS: Record<string, string> = {
  cash: 'Cash',
  momo: 'Mobile Money',
  card: 'Card',
  bank: 'Bank transfer',
  credit: 'Customer credit',
  points: 'Loyalty points',
}

export const MOMO_NETWORKS: { value: string; label: string }[] = [
  { value: 'mtn', label: 'MTN MoMo' },
  { value: 'telecel', label: 'Telecel Cash' },
  { value: 'at', label: 'AT Money' },
]

export const ORDER_TYPE_LABELS: Record<string, string> = {
  retail: 'Retail',
  dine_in: 'Dine in',
  takeaway: 'Takeaway',
  delivery: 'Delivery',
}

export function titleCase(s: string) {
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}
