import { expect, test } from '@playwright/test'

const HARNESS = '/e2e/i18n-harness/'

test('the app is in French and does not expose a language selector yet', async ({ page }) => {
  await page.route('**/api/v1/**', (route) => route.fulfill({ status: 401, json: {} }))
  await page.goto('/')
  await expect(page.locator('html')).toHaveAttribute('lang', 'fr')
  await expect(page.getByRole('combobox', { name: /langue|language/i })).toHaveCount(0)
})

test('browser language is not enough to enable a locale that is hidden', async ({ browser }) => {
  const context = await browser.newContext({ locale: 'en-US' })
  const page = await context.newPage()
  await page.route('**/api/v1/**', (route) => route.fulfill({ status: 401, json: {} }))
  await page.goto('/')
  await expect(page.locator('html')).toHaveAttribute('lang', 'fr')
  await context.close()
})

test('default language, French labels', async ({ page }) => {
  await page.goto(HARNESS)
  await expect(page.getByTestId('one')).toHaveText('1 source disponible')
  await expect(page.getByTestId('many')).toHaveText('1 234 sources disponibles')
  await expect(page.getByTestId('missing')).toHaveText('language.notInEnglishOrFrench')
})

test('switching to English loads the locale, sets the cookie and survives a reload', async ({ page, context }) => {
  await page.goto(HARNESS)
  await page.getByRole('combobox', { name: 'Langue' }).selectOption('en')

  await expect(page.getByTestId('one')).toHaveText('1 source available')
  await expect(page.getByTestId('many')).toHaveText('1,234 sources available')
  await expect(page.getByTestId('number')).toHaveText('1,234,567.5')
  await expect(page.locator('html')).toHaveAttribute('lang', 'en')

  const cookie = (await context.cookies()).find((c) => c.name === 'organon-locale')
  expect(cookie).toMatchObject({ value: 'en', sameSite: 'Lax', path: '/' })
  expect(cookie.expires - Date.now() / 1000).toBeGreaterThan(364 * 86400)

  await page.reload()
  await expect(page.getByTestId('one')).toHaveText('1 source available')
  await expect(page.getByRole('combobox', { name: 'Language' })).toHaveValue('en')
})

test('the cookie wins over the browser language', async ({ page, context }) => {
  await context.addCookies([{ name: 'organon-locale', value: 'en', url: 'http://localhost:5174' }])
  await page.goto(HARNESS)
  await expect(page.getByTestId('one')).toHaveText('1 source available')
})
