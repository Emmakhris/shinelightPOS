import { Button } from './ui'

/** Touch-friendly keypad that edits a numeric string. */
export function NumPad({ value, onChange, allowDecimal = true, keepLeadingZeros = false, onEnter }: {
  value: string
  onChange: (v: string) => void
  allowDecimal?: boolean
  /** For PINs, where 0123 is not the same as 123. */
  keepLeadingZeros?: boolean
  onEnter?: () => void
}) {
  const press = (key: string) => {
    if (key === 'C') return onChange('')
    if (key === '⌫') return onChange(value.slice(0, -1))
    if (key === '.') {
      if (!allowDecimal || value.includes('.')) return
      return onChange(value ? value + '.' : '0.')
    }
    const [, decimals] = value.split('.')
    if (decimals !== undefined && decimals.length >= 2) return
    onChange(value === '0' && !keepLeadingZeros ? key : value + key)
  }
  const keys = ['7', '8', '9', '4', '5', '6', '1', '2', '3', allowDecimal ? '.' : 'C', '0', '⌫']
  return (
    <div className="grid grid-cols-3 gap-2">
      {keys.map((k) => (
        <Button key={k} variant="secondary" size="xl" className="h-14 text-xl" onClick={() => press(k)}>
          {k}
        </Button>
      ))}
      {onEnter && (
        <Button className="col-span-3 h-14" size="xl" onClick={onEnter}>
          Enter
        </Button>
      )}
    </div>
  )
}
