import { useEffect, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { create } from 'zustand'
import type { BusinessSettings, KitchenTicket, Order, Quote, Refund, Sale, ShiftReport } from '../api/types'
import { METHOD_LABELS, ORDER_TYPE_LABELS, dateTime, money, qty, time, titleCase } from '../lib/format'

/**
 * Printing goes through the browser: the document is rendered into #print-root (hidden on
 * screen, the only thing visible when printing) sized for an 80 mm or 58 mm thermal roll.
 */
const usePrintStore = create<{ doc: ReactNode; width: number; nonce: number; print: (doc: ReactNode, width?: number) => void }>(
  (set) => ({
    doc: null,
    width: 80,
    nonce: 0,
    print: (doc, width = 80) => set((s) => ({ doc, width, nonce: s.nonce + 1 })),
  }),
)

export const printDoc = (doc: ReactNode, width?: number) => usePrintStore.getState().print(doc, width)

export function PrintHost() {
  const { doc, width, nonce } = usePrintStore()
  useEffect(() => {
    if (!nonce) return
    document.documentElement.style.setProperty('--paper-width', `${width}mm`)
    // Let React paint the document before opening the print dialog.
    const id = window.setTimeout(() => window.print(), 150)
    return () => window.clearTimeout(id)
  }, [nonce, width])
  const root = document.getElementById('print-root')
  if (!root || !doc) return null
  return createPortal(<div style={{ width: `${width}mm` }}>{doc}</div>, root)
}

function Header({ settings }: { settings: BusinessSettings }) {
  return (
    <div className="center">
      {settings.logo && <img src={settings.logo} alt="" style={{ maxHeight: 50, margin: '0 auto 4px' }} />}
      <div className="big">{settings.name}</div>
      {settings.address && <div style={{ whiteSpace: 'pre-line' }}>{settings.address}</div>}
      {settings.phone && <div>Tel: {settings.phone}</div>}
      {settings.tin && <div>TIN: {settings.tin}</div>}
      {settings.receipt_header && <div style={{ whiteSpace: 'pre-line' }}>{settings.receipt_header}</div>}
    </div>
  )
}

function Row({ left, right, bold }: { left: ReactNode; right: ReactNode; bold?: boolean }) {
  return (
    <div className="row" style={bold ? { fontWeight: 'bold' } : undefined}>
      <span>{left}</span>
      <span style={{ whiteSpace: 'nowrap' }}>{right}</span>
    </div>
  )
}

export function ReceiptDoc({ sale, settings, copy }: { sale: Sale; settings: BusinessSettings; copy?: boolean }) {
  return (
    <div className="receipt">
      <Header settings={settings} />
      <hr />
      <div className="center big">{settings.vat_registered ? 'TAX INVOICE' : 'RECEIPT'}</div>
      {copy && <div className="center">*** COPY ***</div>}
      <Row left="Invoice" right={sale.invoice_number} />
      <Row left="Date" right={dateTime(sale.created_at)} />
      <Row left="Cashier" right={sale.cashier_name} />
      {sale.order_type !== 'retail' && <Row left={ORDER_TYPE_LABELS[sale.order_type]} right={sale.table_name} />}
      {sale.customer_name && <Row left="Customer" right={sale.customer_name} />}
      <hr />
      {sale.lines.map((l) => (
        <div key={l.id} style={{ marginBottom: 2 }}>
          <div>{l.name}</div>
          {l.modifiers.map((m) => (
            <div key={m.id} style={{ paddingLeft: 8 }}>+ {m.name}</div>
          ))}
          <Row left={`  ${qty(l.quantity)} x ${money(l.unit_price, false)}`} right={money(l.total, false)} />
          {Number(l.discount) > 0 && <Row left="  Discount" right={`-${money(l.discount, false)}`} />}
        </div>
      ))}
      <hr />
      <Row left="Subtotal" right={money(sale.subtotal, false)} />
      {Number(sale.discount_total) > 0 && <Row left="Discount" right={`-${money(sale.discount_total, false)}`} />}
      {settings.show_tax_on_receipt &&
        sale.taxes.map((t) => <Row key={t.code} left={`${t.name} ${Number(t.rate)}%`} right={money(t.amount, false)} />)}
      {settings.show_tax_on_receipt && sale.prices_include_tax && Number(sale.tax_total) > 0 && (
        <div style={{ fontSize: 10 }}>(Taxes included in prices)</div>
      )}
      <Row bold left="TOTAL" right={money(sale.total)} />
      <hr />
      {sale.payments.map((p) => (
        <Row
          key={p.id}
          left={`${METHOD_LABELS[p.method]}${p.momo_network ? ` (${p.momo_network.toUpperCase()})` : ''}${p.reference ? ` #${p.reference}` : ''}`}
          right={money(p.amount, false)}
        />
      ))}
      {Number(sale.change_due) > 0 && <Row bold left="Change" right={money(sale.change_due, false)} />}
      {sale.customer_name && Number(sale.points_earned) > 0 && <Row left="Points earned" right={sale.points_earned} />}
      {sale.status === 'voided' && <div className="center big">*** VOIDED ***</div>}
      <hr />
      {settings.receipt_footer && <div className="center" style={{ whiteSpace: 'pre-line' }}>{settings.receipt_footer}</div>}
      <div className="center" style={{ fontSize: 10, marginTop: 4 }}>Powered by ShineLight POS</div>
    </div>
  )
}

export function RefundDoc({ refund, settings }: { refund: Refund; settings: BusinessSettings }) {
  return (
    <div className="receipt">
      <Header settings={settings} />
      <hr />
      <div className="center big">REFUND</div>
      <Row left="Refund" right={refund.number} />
      <Row left="Invoice" right={refund.invoice_number} />
      <Row left="Date" right={dateTime(refund.created_at)} />
      <Row left="By" right={refund.user_name} />
      {refund.approved_by_name && <Row left="Approved" right={refund.approved_by_name} />}
      <hr />
      {refund.lines.map((l) => (
        <Row key={l.sale_line} left={`${qty(l.quantity)} x ${l.name}`} right={money(l.amount, false)} />
      ))}
      <hr />
      <Row bold left={`Refunded (${METHOD_LABELS[refund.method]})`} right={money(refund.amount)} />
      {refund.paystack && <div>Sent through Paystack to {refund.paystack.phone}. It can take up to 10 business days to arrive.</div>}
      <div>Reason: {refund.reason}</div>
    </div>
  )
}

export function KitchenTicketDoc({ ticket }: { ticket: KitchenTicket }) {
  return (
    <div className="receipt" style={{ fontSize: 14 }}>
      <div className="center big">KITCHEN #{ticket.number}</div>
      <Row left={ticket.table_name ? `Table ${ticket.table_name}` : ORDER_TYPE_LABELS[ticket.order_type]} right={`Order ${ticket.order_number}`} />
      <Row left={ticket.waiter_name ?? ''} right={time(ticket.created_at)} />
      <hr />
      {ticket.items.map((i) => (
        <div key={i.id} style={{ marginBottom: 4 }}>
          <div className="big">
            {qty(i.quantity)} x {i.name}
          </div>
          {i.modifier_details.map((m) => (
            <div key={m.id} style={{ paddingLeft: 12 }}>+ {m.name}</div>
          ))}
          {i.note && <div style={{ paddingLeft: 12, fontStyle: 'italic' }}>** {i.note}</div>}
        </div>
      ))}
    </div>
  )
}

export function BillDoc({ order, quote, settings }: { order: Order; quote: Quote; settings: BusinessSettings }) {
  return (
    <div className="receipt">
      <Header settings={settings} />
      <hr />
      <div className="center big">BILL</div>
      <Row left={order.table_name ? `Table ${order.table_name}` : ORDER_TYPE_LABELS[order.order_type]} right={`Order ${order.number}`} />
      <Row left="Guests" right={order.guests} />
      <Row left="Printed" right={dateTime(new Date().toISOString())} />
      <hr />
      {quote.lines.map((l, i) => (
        <Row key={i} left={`${qty(l.quantity)} x ${l.name}`} right={money(l.total, false)} />
      ))}
      <hr />
      {Number(quote.discount_total) > 0 && <Row left="Discount" right={`-${money(quote.discount_total, false)}`} />}
      {settings.show_tax_on_receipt && quote.taxes.map((t) => <Row key={t.code} left={`${t.name} ${Number(t.rate)}%`} right={money(t.amount, false)} />)}
      <Row bold left="TOTAL DUE" right={money(quote.total)} />
      <hr />
      <div className="center">This is not a receipt.</div>
    </div>
  )
}

export function ShiftReportDoc({ report, settings, title }: { report: ShiftReport; settings: BusinessSettings; title: string }) {
  return (
    <div className="receipt">
      <div className="center big">{settings.name}</div>
      <div className="center big">{title}</div>
      {report.cashier && <Row left="Cashier" right={report.cashier} />}
      {report.opened_at && <Row left="Opened" right={dateTime(report.opened_at)} />}
      {report.closed_at && <Row left="Closed" right={dateTime(report.closed_at)} />}
      <Row left="Printed" right={dateTime(new Date().toISOString())} />
      <hr />
      <Row left="Sales" right={report.sales_count} />
      <Row left="Items sold" right={report.items_sold} />
      <Row left="Gross sales" right={money(report.gross_sales, false)} />
      <Row left="Discounts" right={money(report.discounts, false)} />
      <Row left="Tax" right={money(report.tax, false)} />
      <Row left="Net sales (ex tax)" right={money(report.net_sales, false)} />
      <Row left="Refunds" right={money(report.refunds, false)} />
      <Row left={`Voids (${report.voided_count})`} right={money(report.voided_total, false)} />
      <hr />
      <div>PAYMENTS</div>
      {Object.entries(report.payments).map(([k, v]) => (
        <Row key={k} left={METHOD_LABELS[k] ?? k} right={money(v, false)} />
      ))}
      {Object.entries(report.balance_payments).map(([k, v]) => (
        <Row key={k} left={`Debt paid (${METHOD_LABELS[k] ?? k})`} right={money(v, false)} />
      ))}
      <hr />
      <div>TAXES</div>
      {report.taxes.map((t) => (
        <Row key={t.code} left={t.name} right={money(t.amount, false)} />
      ))}
      {report.expected_cash !== undefined && (
        <>
          <hr />
          <div>CASH DRAWER</div>
          <Row left="Opening float" right={money(report.opening_float, false)} />
          <Row left="Cash in" right={money(report.cash_in, false)} />
          <Row left="Cash out" right={money(report.cash_out, false)} />
          <Row left="Drops" right={money(report.cash_drops, false)} />
          <Row left="Cash refunds" right={money(report.refunds_by_method.cash ?? 0, false)} />
          <Row bold left="Expected cash" right={money(report.expected_cash, false)} />
          {report.counted_cash != null && <Row left="Counted cash" right={money(report.counted_cash, false)} />}
          {report.difference != null && (
            <Row bold left={Number(report.difference) < 0 ? 'SHORT' : 'OVER'} right={money(report.difference, false)} />
          )}
        </>
      )}
      <hr />
      <div className="center">{titleCase(report.type === 'Z' ? 'end of shift' : 'mid shift')}</div>
    </div>
  )
}
