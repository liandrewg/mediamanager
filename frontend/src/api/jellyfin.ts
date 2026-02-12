import client from './client'

export async function getLibraryMovies(page = 1, limit = 50, search?: string) {
  const params: Record<string, string | number> = { page, limit }
  if (search) params.search = search
  const { data } = await client.get('/library/movies', { params })
  return data
}

export async function getLibraryTvShows(page = 1, limit = 50, search?: string) {
  const params: Record<string, string | number> = { page, limit }
  if (search) params.search = search
  const { data } = await client.get('/library/tvshows', { params })
  return data
}

export async function getLibraryStats() {
  const { data } = await client.get('/library/stats')
  return data
}

export async function getRecentlyAdded(limit = 20) {
  const { data } = await client.get('/library/recent', { params: { limit } })
  return data
}
