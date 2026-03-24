import { test, expect } from '@playwright/test'

test('unauthenticated user is redirected to login from protected routes', async ({ page }) => {
  await page.goto('/search')

  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByText('Sign in with your Jellyfin account')).toBeVisible()
})
