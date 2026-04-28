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

export interface PreflightVerdict {
  code:
    | 'watch_now'
    | 'already_supporting'
    | 'join_queue'
    | 'fresh_request'
    | 'recently_added'
  headline: string
  detail?: string
  primary_action: 'watch' | 'join' | 'request' | 'view_request'
  primary_action_url?: string | null
  primary_action_label?: string | null
  request_disabled: boolean
}

export interface PreflightCommunityRequest {
  id: number
  status: string
  supporter_count: number
  user_supporting: boolean
  is_owner: boolean
  days_open: number
  created_at: string
  queue_position?: number | null
  queue_size?: number | null
}

export interface PreflightEta {
  start_days: number
  end_days: number
  label: string
  confidence?: string | null
  source?: string | null
  sample_size?: number | null
}

export interface PreflightRecentlyFulfilled {
  request_id: number
  title: string
  fulfilled_at: string
  age_days: number
  jellyfin_item_id?: string | null
  watch_url?: string | null
}

export interface RequestPreflight {
  tmdb_id: number
  media_type: string
  in_library: boolean
  library_watch_url?: string | null
  community_request?: PreflightCommunityRequest | null
  eta?: PreflightEta | null
  recently_fulfilled?: PreflightRecentlyFulfilled | null
  verdict: PreflightVerdict
}

export async function getRequestPreflight(
  mediaType: 'movie' | 'tv' | 'book',
  tmdbId: number,
): Promise<RequestPreflight> {
  const { data } = await client.get(`/tmdb/preflight/${mediaType}/${tmdbId}`)
  return data as RequestPreflight
}
