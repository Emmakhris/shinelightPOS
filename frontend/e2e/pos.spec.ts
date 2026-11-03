import { expect, test, type Page } from '@playwright/test'

/**
 * One shop day on a fresh database, driven through the real UI:
 * setup → retail sale (scan, modifiers, MoMo + cash) → refund → restaurant order → close shift → reports.
 * The steps share a page and build on each other, so they run in order.
 */
test.describe.configure({ mode: 'serial' })

let page: Page

const printed = () => page.evaluate(() => document.getElementById('print-root')?.innerText ?? '')
const dialog = () => page.getByRole('dialog').last()
const key = (scope: ReturnType<typeof dialog>, k: string) => scope.getByRole('button', { name: k, exact: true }).click()
const typeOnPad = async (digits: string) => {
  for (const d of digits) await key(dialog(), d)
}

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage()
  // Thermal printing opens the browser's print dialog; record the printout instead.
  await page.addInitScript(() => {
    window.print = () => {
      ;(window as unknown as { __prints: number }).__prints = ((window as unknown as { __prints?: number }).__prints ?? 0) + 1
    }
  })
  // "Print refund slip?" and similar prompts: answer no.
  page.on('dialog', (d) => d.dismiss())
})

test.afterAll(async () => {
  await page.close()
})

test('first-run setup creates the business and signs the owner in', async () => {
  await page.goto('/')
  await page.getByLabel('Business name').fill('E2E Mart')
  await page.getByLabel('Business email').fill('shop@example.com')
  await page.getByLabel('Restaurant / bar').check()
  await page.getByLabel('VAT registered with GRA').check()
  await page.getByRole('button', { name: 'Next' }).click()

  await page.getByLabel('First name').fill('Ama')
  await page.getByLabel('Username').fill('owner')
  await page.getByLabel('Password').fill('owner123')
  await page.getByLabel('PIN', { exact: false }).fill('1234')
  await page.getByRole('button', { name: 'Finish setup' }).click()

  await expect(page.getByRole('heading', { name: /Good (morning|afternoon|evening)/ })).toBeVisible()
})

test('backups: the dashboard warns until a backup is made', async () => {
  await expect(page.getByText('No backup has been made yet.')).toBeVisible()
  await page.goto('/settings')
  await page.getByRole('button', { name: 'Backups', exact: true }).click()
  await page.getByRole('button', { name: 'Back up now' }).click()
  await expect(page.getByText('Backup complete')).toBeVisible()
  await expect(page.getByRole('row', { name: /_manual/ })).toBeVisible()
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /Good/ })).toBeVisible()
  await expect(page.getByText('No backup has been made yet.')).toHaveCount(0)
})

test('retail sale: scan, add options, Paystack MoMo prompt plus cash, give change', async () => {
  await page.goto('/pos')
  await page.getByRole('button', { name: 'Open shift to start selling' }).click()
  await typeOnPad('200')
  await dialog().getByRole('button', { name: 'Open shift', exact: true }).click()
  await expect(page.getByRole('button', { name: /^Pay/ })).toBeVisible()

  const scan = page.getByPlaceholder('Scan barcode or search products…')
  await scan.fill('5449000000996') // Coca-Cola 500ml
  await scan.press('Enter')
  await scan.fill('5449000000996')
  await scan.press('Enter')

  await scan.fill('Jollof')
  await page.getByRole('button', { name: /Jollof Rice/ }).click()
  await dialog().getByRole('button', { name: /Chicken/ }).click()
  await dialog().getByRole('button', { name: /Shito/ }).click()
  await dialog().getByRole('button', { name: 'Add GH₵ 29.00' }).click()

  // 2 x 8.00 + (12.00 + 15.00 chicken + 2.00 shito)
  await expect(page.getByRole('button', { name: 'Pay GH₵ 45.00' })).toBeEnabled()
  await page.getByRole('button', { name: 'Pay GH₵ 45.00' }).click()

  await dialog().getByRole('button', { name: 'Mobile Money' }).click()
  await expect(dialog().getByText('Paystack simulator: no real money is taken.')).toBeVisible()
  await typeOnPad('20')
  await dialog().getByRole('button', { name: 'Send MoMo prompt' }).click()

  // The simulator declines numbers ending in 0000: the cashier sees why and tries another number.
  const prompt = dialog()
  await expect(prompt.getByText('MoMo prompt · GH₵ 20.00')).toBeVisible()
  await prompt.getByLabel("Customer's MoMo number").fill('0240000000')
  await prompt.getByRole('button', { name: 'Send prompt to phone' }).click()
  await expect(prompt.getByText('Waiting for the customer to approve…')).toBeVisible()
  await expect(prompt.getByText(/Payment failed: Declined by customer/)).toBeVisible()
  await prompt.getByLabel("Customer's MoMo number").fill('0241234567')
  await prompt.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByText('MoMo payment of GH₵ 20.00 received')).toBeVisible()
  await expect(dialog().getByText('✓ Paystack')).toBeVisible()

  await dialog().getByRole('button', { name: '50.00', exact: true }).click()
  await dialog().getByRole('button', { name: 'Complete sale' }).click()

  await expect(dialog().getByText('Sale complete')).toBeVisible()
  await expect(dialog().getByText('INV-MAIN-000001')).toBeVisible()
  await expect(dialog().getByText('GH₵ 25.00')).toBeVisible() // change
  await dialog().getByRole('button', { name: '🖨 Print receipt' }).click()
  await expect.poll(printed).toContain('TAX INVOICE')
  expect(await printed()).toMatch(/Mobile Money \(MTN\) #SLP-/)
  await dialog().getByRole('button', { name: 'New sale' }).click()
})

test('partial refund in cash puts stock back and marks the sale', async () => {
  await page.goto('/sales')
  await page.getByRole('cell', { name: 'INV-MAIN-000001' }).click()
  await dialog().getByRole('button', { name: 'Refund…' }).click()

  const refund = dialog()
  await refund.getByRole('spinbutton').first().fill('1') // one Coca-Cola
  await refund.getByLabel('Refund by').selectOption('cash')
  await refund.getByLabel('Reason').fill('Damaged can')
  await refund.getByRole('button', { name: 'Refund', exact: true }).click()

  await expect(page.getByText('Refunded GH₵ 8.00')).toBeVisible()
  await expect(dialog().getByText('Partly refunded')).toBeVisible()
  await expect(dialog().getByText('1 refunded')).toBeVisible()
})

test('restaurant: open a table, send food to the kitchen, pay the bill', async () => {
  await page.goto('/tables')
  await page.getByRole('button', { name: /^T3\b/ }).click()
  await dialog().getByRole('button', { name: 'Start order' }).click()
  await expect(page).toHaveURL(/\/tables\/order\/\d+/)

  await page.getByRole('button', { name: /Kelewele/ }).click()
  await expect(page.getByText('1 × Kelewele')).toBeVisible()
  await page.getByRole('button', { name: /Kelewele/ }).click()
  await expect(page.getByText('2 × Kelewele')).toBeVisible()
  await page.getByRole('button', { name: /Malta Guinness/ }).click()
  await expect(page.getByText('1 × Malta Guinness 330ml')).toBeVisible()

  await page.getByRole('button', { name: /Send to kitchen/ }).click()
  await expect.poll(printed).toContain('KITCHEN #1')
  const ticket = await printed()
  expect(ticket).toContain('2 x Kelewele')
  expect(ticket).not.toContain('Malta') // drinks are not kitchen items

  await page.getByRole('button', { name: 'Pay GH₵ 30.00' }).click()
  await dialog().getByRole('button', { name: 'Exact' }).click()
  await dialog().getByRole('button', { name: 'Complete sale' }).click()
  await expect(dialog().getByText('INV-MAIN-000002')).toBeVisible()
  await dialog().getByRole('button', { name: 'New sale' }).click()

  await expect(page).toHaveURL(/\/tables$/)
  await expect(page.getByRole('button', { name: /^T3\b/ })).toContainText('Free')
})

test('closing the shift reports expected cash and the shortage', async () => {
  await page.goto('/shifts')
  // 200 float + 25 kept from sale 1 (50 - 25 change) - 8 cash refund + 30 table bill
  await expect(page.getByText('Cash expected in drawer').locator('..')).toContainText('GH₵ 247.00')

  await page.getByRole('button', { name: 'Close shift' }).click()
  await typeOnPad('245')
  await expect(dialog().getByText('Short by GH₵ 2.00')).toBeVisible()
  await dialog().getByRole('button', { name: 'Close & print Z report' }).click()

  await expect(page.getByText('Shift closed')).toBeVisible()
  await expect.poll(printed).toContain('Z REPORT')
  const z = await printed()
  expect(z).toMatch(/Expected cash\s*247\.00/)
  expect(z).toMatch(/SHORT\s*-2\.00/)
  await expect(page.getByRole('button', { name: 'Open shift' })).toBeVisible()
})

test('reports add up the day', async () => {
  await page.goto('/reports')
  const stat = (label: string) => page.getByText(label, { exact: true }).locator('..')
  await expect(stat('Gross sales')).toContainText('GH₵ 75.00')
  await expect(stat('Tax collected')).toContainText('GH₵ 12.50') // 20% inside tax-inclusive prices
  await expect(stat('Refunds')).toContainText('GH₵ 8.00')

  // Paystack reconciliation: the approved prompt is on sale 1, the declined one is listed as failed.
  await page.getByRole('button', { name: 'Payments', exact: true }).click()
  await expect(page.getByRole('row', { name: /0241234567/ })).toContainText('INV-MAIN-000001')
  await expect(page.getByRole('row', { name: /0240000000/ })).toContainText('Failed')
  await expect(page.getByText(/paid but not on a sale/)).toHaveCount(0)

  await page.getByRole('button', { name: 'Tax (GRA)' }).click()
  await expect(page.getByRole('row', { name: /VAT/ })).toContainText('GH₵ 9.38')
})
