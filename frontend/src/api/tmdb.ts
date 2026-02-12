import client from './client'

export async function searchMedia(query: string, page = 1, type?: string) {
  const params: Record<string, string | number> = { query, page }
  if (type) params.type = type
  const { data } = await client.get('/tmdb/search', { params })
  return data
}

export async function getMovieDetails(tmdbId: number) {
  const { data } = await client.get(`/tmdb/movie/${tmdbId}`)
  return data
}

export async function getTvDetails(tmdbId: number) {
  const { data } = await client.get(`/tmdb/tv/${tmdbId}`)
  return data
}
