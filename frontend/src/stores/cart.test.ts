import { beforeEach, describe, expect, it } from 'vitest'
import type { PosItem } from '../api/types'
import { cartDiscount, cartTotal, lineDiscount, lineTotal, toApiLines, unitPrice, useCart } from './cart'

const item = (id: number, price: string): PosItem => ({
  id, product_id: id, name: `Item ${id}`, product_name: `Item ${id}`, variant_name: '', sku: null, price,
  barcodes: [], category: null, category_color: null, tax_category: 'standard', unit: 'pc',
  allows_fraction: false, track_stock: true, stock: '10', is_kitchen_item: false, image: null, modifier_groups: [],
})

describe('cart store', () => {
  beforeEach(() => useCart.getState().clear())

  it('adds the same item to one line and keeps modifier combinations apart', () => {
    const cart = useCart.getState()
    cart.add(item(1, '12.00'))
    cart.add(item(1, '12.00'))
    cart.add(item(1, '12.00'), [{ id: 5, name: 'Chicken', price: '15.00' }])
    const lines = useCart.getState().lines
    expect(lines).toHaveLength(2)
    expect(lines[0].quantity).toBe(2)
    expect(unitPrice(lines[1])).toBe(27)
  })

  it('applies line and cart discounts', () => {
    const cart = useCart.getState()
    cart.add(item(1, '12.00'), [], 3)
    cart.add(item(2, '9.99'))
    const [a] = useCart.getState().lines
    cart.update(a.key, { discountType: 'percent', discountValue: 10 })
    cart.setDiscount('amount', 5)
    const state = useCart.getState()
    expect(lineDiscount(state.lines[0])).toBe(3.6)
    expect(lineTotal(state.lines[0])).toBe(32.4)
    expect(cartDiscount(state)).toBe(5)
    expect(cartTotal(state)).toBe(37.39)
  })

  it('never discounts more than the value', () => {
    const cart = useCart.getState()
    cart.add(item(1, '10.00'))
    const [a] = useCart.getState().lines
    cart.update(a.key, { discountValue: 50 })
    cart.setDiscount('percent', 150)
    const state = useCart.getState()
    expect(lineTotal(state.lines[0])).toBe(0)
    expect(cartTotal(state)).toBe(0)
  })

  it('serialises lines for the API', () => {
    useCart.getState().add(item(7, '4.00'), [{ id: 2, name: 'x', price: '1.00' }], 2)
    expect(toApiLines(useCart.getState().lines)[0]).toMatchObject({
      variant: 7, quantity: '2', modifiers: [2], unit_price: null,
    })
  })
})
