// Shapes returned by the Django API. Money and quantities arrive as decimal strings.

export type Role = 'owner' | 'manager' | 'cashier' | 'waiter'

export interface User {
  id: number
  username: string
  first_name: string
  last_name: string
  display_name: string
  email: string
  phone: string
  role: Role
  is_active: boolean
  has_pin: boolean
  permissions: string[]
  last_login: string | null
}

export interface BusinessSettings {
  name: string
  legal_name: string
  tin: string
  vat_registered: boolean
  address: string
  phone: string
  email: string
  logo: string | null
  currency_code: string
  currency_symbol: string
  retail_mode: boolean
  restaurant_mode: boolean
  prices_include_tax: boolean
  allow_negative_stock: boolean
  require_open_shift: boolean
  discount_approval_percent: string
  loyalty_enabled: boolean
  loyalty_points_per_cedi: string
  loyalty_point_value: string
  receipt_header: string
  receipt_footer: string
  receipt_width: 80 | 58
  show_tax_on_receipt: boolean
  setup_complete: boolean
  /** null = Paystack not set up; "simulated" = built-in simulator (sk_fake). */
  paystack_mode: 'live' | 'test' | 'simulated' | null
}

export interface PaystackCharge {
  reference: string
  amount: string
  currency: string
  phone: string
  network: string
  status: 'pending' | 'pay_offline' | 'send_otp' | 'success' | 'failed' | 'abandoned'
  status_label: string
  display_text: string
  message: string
  created_at: string
  paid_at: string | null
  invoice_number: string | null
  sale: number | null
  created_by_name: string | null
}

export interface TaxRate {
  id: number
  name: string
  code: string
  rate: string
  compound: boolean
  sort_order: number
  is_active: boolean
}

export interface Category {
  id: number
  name: string
  color: string
  sort_order: number
  is_active: boolean
  product_count?: number
}

export interface Modifier {
  id?: number
  name: string
  price: string
  is_active: boolean
  sort_order: number
}

export interface ModifierGroup {
  id: number
  name: string
  min_select: number
  max_select: number
  sort_order: number
  modifiers: Modifier[]
}

export type TaxCategory = 'standard' | 'zero' | 'exempt'

export interface Variant {
  id?: number
  name: string
  sku: string | null
  price: string
  cost_price: string
  is_active: boolean
  sort_order: number
  barcodes: string[]
  stock?: string | null
  opening_stock?: string
}

export interface Product {
  id: number
  name: string
  category: number | null
  category_name: string | null
  description: string
  unit: string
  tax_category: TaxCategory
  track_stock: boolean
  low_stock_threshold: string
  has_variants: boolean
  is_kitchen_item: boolean
  modifier_groups: number[]
  image: string | null
  is_active: boolean
  variants: Variant[]
}

/** A sellable variant as the register sees it. */
export interface PosItem {
  id: number
  product_id: number
  name: string
  product_name: string
  variant_name: string
  sku: string | null
  price: string
  barcodes: string[]
  category: number | null
  category_color: string | null
  tax_category: TaxCategory
  unit: string
  allows_fraction: boolean
  track_stock: boolean
  stock: string
  is_kitchen_item: boolean
  image: string | null
  modifier_groups: number[]
}

export interface Customer {
  id: number
  name: string
  phone: string | null
  email: string
  address: string
  notes: string
  loyalty_points: string
  credit_limit: string
  balance: string
  is_active: boolean
  created_at: string
}

export interface CustomerTransaction {
  id: number
  created_at: string
  kind: string
  kind_label: string
  amount: string
  points: string
  method: string
  reference: string
  sale: number | null
  invoice_number: string | null
  note: string
  user_name: string | null
}

export type PaymentMethod = 'cash' | 'momo' | 'card' | 'bank' | 'credit' | 'points'

export interface PaymentInput {
  method: PaymentMethod
  amount: string
  momo_network?: string
  reference?: string
  /** Set when the money was taken through a Paystack MoMo prompt; the server re-checks it. */
  paystack_reference?: string
}

export interface Quote {
  subtotal: string
  discount_total: string
  tax_total: string
  total: string
  taxes: { code: string; name: string; rate: string; amount: string }[]
  lines: { variant: number; name: string; quantity: string; unit_price: string; discount: string; total: string }[]
}

export interface SaleLine {
  id: number
  variant: number
  name: string
  sku: string
  quantity: string
  unit_price: string
  modifiers: { id: number; name: string; price: string }[]
  discount: string
  net_amount: string
  tax_amount: string
  total: string
  tax_category: TaxCategory
  refunded_quantity: string
  note: string
}

export interface Payment {
  id: number
  method: PaymentMethod
  method_label: string
  amount: string
  momo_network: string
  reference: string
}

export interface Refund {
  id: number
  number: string
  sale: number
  invoice_number: string
  method: PaymentMethod
  reference: string
  amount: string
  tax_amount: string
  reason: string
  restocked: boolean
  created_at: string
  user_name: string
  approved_by_name: string | null
  lines: { sale_line: number; name: string; quantity: string; amount: string }[]
}

export type SaleStatus = 'completed' | 'partially_refunded' | 'refunded' | 'voided'

export interface SaleSummary {
  id: number
  invoice_number: string
  created_at: string
  status: SaleStatus
  status_label: string
  order_type: string
  table_name: string
  cashier_name: string
  customer: number | null
  customer_name: string | null
  total: string
  payment_methods: PaymentMethod[]
}

export interface Sale extends SaleSummary {
  prices_include_tax: boolean
  subtotal: string
  discount_total: string
  tax_total: string
  paid_total: string
  change_due: string
  cost_total: string
  points_earned: string
  points_redeemed: string
  note: string
  approved_by_name: string | null
  voided_at: string | null
  voided_by_name: string | null
  void_reason: string
  customer_phone: string | null
  lines: SaleLine[]
  taxes: { code: string; name: string; rate: string; amount: string }[]
  payments: Payment[]
  refunds: Refund[]
}

export interface HeldSale {
  id: number
  label: string
  user_name: string
  customer: number | null
  customer_name: string | null
  cart: unknown
  created_at: string
}

export interface Shift {
  id: number
  user: number
  user_name: string
  register_name: string
  status: 'open' | 'closed'
  opened_at: string
  closed_at: string | null
  opening_float: string
  expected_cash: string | null
  counted_cash: string | null
  difference: string | null
  closing_note: string
  closed_by_name: string | null
}

export interface CashMovement {
  id: number
  kind: 'paid_in' | 'paid_out' | 'drop'
  kind_label: string
  amount: string
  reason: string
  user_name: string | null
  created_at: string
}

export interface ShiftReport {
  type?: 'X' | 'Z'
  shift_id?: number
  cashier?: string
  register_name?: string
  status?: string
  opened_at?: string
  closed_at?: string | null
  counted_cash?: string | null
  difference?: string | null
  sales_count: number
  items_sold: string
  gross_sales: string
  subtotal: string
  discounts: string
  tax: string
  net_sales: string
  cost_of_sales: string
  refunds: string
  refunds_by_method: Record<string, string>
  net_after_refunds: string
  voided_count: number
  voided_total: string
  payments: Record<string, string>
  balance_payments: Record<string, string>
  taxes: { code: string; name: string; amount: string }[]
  opening_float?: string
  cash_in: string
  cash_out: string
  cash_drops: string
  expected_cash?: string
}

export interface StockRow {
  variant: number
  name: string
  sku: string
  category: string
  unit: string
  quantity: string
  low_stock_threshold: string
  is_low: boolean
  cost_price: string
  price: string
  stock_value: string
}

export interface StockMovement {
  id: number
  created_at: string
  variant: number
  variant_name: string
  change: string
  quantity_after: string
  reason: string
  reason_label: string
  reference: string
  unit_cost: string
  note: string
  user_name: string | null
}

export interface Supplier {
  id: number
  name: string
  contact_name: string
  phone: string
  email: string
  address: string
  notes: string
  is_active: boolean
}

export interface PurchaseOrderLine {
  id?: number
  variant: number
  variant_name?: string
  quantity_ordered: string
  quantity_received?: string
  unit_cost: string
}

export interface PurchaseOrder {
  id: number
  number: string
  supplier: number
  supplier_name: string
  status: 'draft' | 'ordered' | 'partial' | 'received' | 'cancelled'
  expected_date: string | null
  supplier_invoice: string
  notes: string
  created_at: string
  lines: PurchaseOrderLine[]
  total: string
}

export interface FloorArea {
  id: number
  name: string
  sort_order: number
}

export interface Table {
  id: number
  area: number
  name: string
  seats: number
  sort_order: number
  is_active: boolean
}

export interface OrderItem {
  id: number
  variant: number
  name: string
  quantity: string
  modifiers: number[]
  modifier_details: { id: number; name: string; price: string }[]
  unit_price: string
  note: string
  status: 'pending' | 'sent' | 'cancelled'
  status_label: string
  is_kitchen_item: boolean
  created_at: string
}

export interface Order {
  id: number
  number: string
  table: number | null
  table_name: string | null
  order_type: 'dine_in' | 'takeaway' | 'delivery'
  status: 'open' | 'paid' | 'cancelled'
  waiter_name: string
  customer: number | null
  customer_name: string | null
  customer_label: string
  guests: number
  note: string
  created_at: string
  items: OrderItem[]
  estimated_total: string
  pending_count: number
  sale: number | null
}

export interface KitchenTicket {
  id: number
  number: number
  order: number
  order_number: string
  table_name: string | null
  order_type: string
  waiter_name: string | null
  created_at: string
  items: OrderItem[]
}

export interface FloorAreaWithTables extends FloorArea {
  tables: (Table & { order: Order | null })[]
}

export interface AuditEntry {
  id: number
  created_at: string
  user_name: string | null
  approved_by_name: string | null
  action: string
  entity: string
  entity_id: string
  details: Record<string, unknown>
}

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}
