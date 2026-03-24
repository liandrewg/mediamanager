import { test, expect } from '@playwright/test'

test('user can log in and navigate core pages with mocked API', async ({ page }) => {
  await page.route('**/api/auth/login', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        token: 'e2e-token',
        user: { id: '1', username: 'e2e-user', is_admin: false },
      }),
    })
  })

  await page.route('**/api/**', async (route) => {
    const url = route.request().url()

    if (url.includes('/api/library/stats')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ total_movies: 120, total_shows: 35, total_episodes: 800 }),
      })
    }

    if (url.includes('/api/library/recent')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      })
    }

    if (url.includes('/api/requests')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0, page: 1, limit: 5 }),
      })
    }

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    })
  })

  await page.goto('/login')
  await page.getByLabel('Username').fill('e2e-user')
  await page.getByLabel('Password').fill('test-password')
  await page.getByRole('button', { name: 'Sign In' }).click()

  await expect(page).toHaveURL('/')
  await expect(page.getByRole('heading', { name: /Welcome, e2e-user/i })).toBeVisible()

  await page.getByRole('link', { name: 'Search' }).click()
  await expect(page).toHaveURL(/\/search$/)
  await expect(page.getByRole('heading', { name: 'Search' })).toBeVisible()

  await page.getByRole('link', { name: 'Library' }).click()
  await expect(page).toHaveURL(/\/library$/)
  await expect(page.getByRole('heading', { name: 'Library' })).toBeVisible()
})
