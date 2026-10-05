import { expect, test } from '@playwright/test'

// Primary pages must share the same layout: container position/width,
// first content element position, and a scrollbar gutter that does not
// shift content between short and long pages. Tolerance: 1px.
const TOLERANCE = 1

function source(i) {
  return {
    id: `src${i}`,
    name: `Source ${i}`,
    url: null,
    status: 'disponible',
    is_default: false,
    access: { type: 'api_rest', detail: 'API' },
    classification: { can_classify: true, estimated: false },
    harvested_items: ['Auteur', 'Rang', `Élément propre ${i}`],
  }
}

// Enough rows for the Sources page to overflow the viewport; the other
// pages are short.
const SOURCES = { last_updated: '2026-01-01', categories: [{ name: 'Test', sources: Array.from({ length: 40 }, (_, i) => source(i)) }] }

const ROUTES = {
  '/api/v1/auth/me': { authenticated: true, username: 'Testeur' },
  '/api/v1/domains': [],
  '/api/v1/modules': [],
  '/api/v1/sources': SOURCES,
}

const PAGES = [
  { name: 'accueil', first: '.eyebrow', open: async () => {} },
  { name: 'sources', first: '.back-link', open: (page) => page.getByRole('button', { name: /source.* disponible/ }).click() },
  { name: 'auteurs', first: '.back-link', open: (page) => page.getByRole('button', { name: 'Auteurs et crédits' }).click() },
]

async function measure(page, first) {
  return page.evaluate((firstSelector) => {
    const rect = (selector) => {
      const r = document.querySelector(selector).getBoundingClientRect()
      return { left: r.left, top: r.top, width: r.width }
    }
    const scroller = document.querySelector('.page-scroll')
    return {
      main: rect('main'),
      topbar: rect('.topbar'),
      first: rect(firstSelector),
      headerTop: document.querySelector('header').getBoundingClientRect().top,
      footerHeight: document.querySelector('footer').getBoundingClientRect().height,
      footerBottom: document.querySelector('footer').getBoundingClientRect().bottom,
      clientWidth: scroller.clientWidth,
      overflows: scroller.scrollHeight > scroller.clientHeight,
    }
  }, first)
}

// The storage banner is fixed at the bottom and would cover the footer links.
async function goHome(page) {
  await page.goto('/')
  // Consent is remembered after the first refusal: the banner only shows once.
  const refuse = page.getByRole('button', { name: 'Refuser' })
  if (await refuse.count()) await refuse.click()
}

async function mockApi(page) {
  await page.route('**/api/v1/**', (route) => {
    const body = ROUTES[new URL(route.request().url()).pathname]
    if (body === undefined) return route.fulfill({ status: 404, json: { detail: 'not found' } })
    return route.fulfill({ json: body })
  })
}

test('les pages principales partagent la même mise en page', async ({ page }) => {
  await mockApi(page)

  const measures = {}
  for (const { name, first, open } of PAGES) {
    await goHome(page)
    await expect(page.locator('.eyebrow')).toBeVisible()
    await open(page)
    await expect(page.locator(first)).toBeVisible()
    await page.waitForLoadState('networkidle')
    measures[name] = await measure(page, first)
  }

  // Guard: the comparison is only meaningful if both kinds of page exist.
  expect(measures.sources.overflows).toBe(true)
  expect(Object.values(measures).some((m) => !m.overflows)).toBe(true)

  // Desktop: header and footer pinned to the window on every page, long or short.
  for (const [name, m] of Object.entries(measures)) {
    expect(Math.abs(m.footerBottom - 720), `${name} : pied de page`).toBeLessThanOrEqual(TOLERANCE)
    expect(m.footerHeight, `${name} : pied de page sur une ligne`).toBeLessThan(60)
    expect(Math.abs(m.headerTop), `${name} : en-tête`).toBeLessThanOrEqual(TOLERANCE)
  }

  const ref = measures.accueil
  for (const [name, m] of Object.entries(measures)) {
    for (const [label, got, want] of [
      ['main.left', m.main.left, ref.main.left],
      ['main.width', m.main.width, ref.main.width],
      ['topbar.left', m.topbar.left, ref.topbar.left],
      ['topbar.width', m.topbar.width, ref.topbar.width],
      ['premier élément left', m.first.left, ref.first.left],
      ['premier élément top', m.first.top, ref.first.top],
      ['clientWidth', m.clientWidth, ref.clientWidth],
    ]) {
      expect(Math.abs(got - want), `${name} : ${label} = ${got} (accueil : ${want})`).toBeLessThanOrEqual(TOLERANCE)
    }
  }
})

test('mobile : la fenêtre défile et le pied de page suit le contenu', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 })
  await mockApi(page)
  await goHome(page)
  await page.getByRole('button', { name: /source.* disponible/ }).click()
  await expect(page.locator('.back-link')).toBeVisible()
  await page.waitForLoadState('networkidle')

  const { windowScrolls, footerTop, contentBottom } = await page.evaluate(() => ({
    windowScrolls: document.documentElement.scrollHeight > window.innerHeight,
    footerTop: document.querySelector('footer').getBoundingClientRect().top + window.scrollY,
    contentBottom: document.querySelector('main').getBoundingClientRect().bottom + window.scrollY,
  }))
  expect(windowScrolls).toBe(true)
  expect(footerTop).toBeGreaterThanOrEqual(contentBottom - TOLERANCE)
})
