import client from './client'

export interface ContinuationCandidate {
  tmdb_id: number
  title: string
  poster_path: string | null
  fulfilled_at: string | null
  last_seen_seasons: number
  last_aired_seasons: number
  dismissed_through: number
  new_seasons: number
  tmdb_status: string | null
  last_air_date: string | null
  checked_at: string | null
  original_request_id: number | null
  household_supporters: number
}

export interface RadarRefreshSummary {
  checked: number
  candidates: number
  errors: number
  skipped_recent: number
}

export interface RadarResponse {
  candidates: ContinuationCandidate[]
  count: number
  refresh: RadarRefreshSummary | null
}

export async function getSeriesContinuationRadar(refresh = false): Promise<RadarResponse> {
  const { data } = await client.get('/admin/series-continuation', {
    params: refresh ? { refresh: true } : undefined,
  })
  return data
}

export async function queueSeriesContinuation(tmdbId: number) {
  const { data } = await client.post(`/admin/series-continuation/${tmdbId}/queue`)
  return data
}

export async function dismissSeriesContinuation(tmdbId: number, throughSeasons?: number) {
  const { data } = await client.post(`/admin/series-continuation/${tmdbId}/dismiss`, {
    through_seasons: throughSeasons ?? null,
  })
  return data
}
