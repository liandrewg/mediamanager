import client from './client'

export interface CreateRequestBody {
  tmdb_id: number
  media_type: string
  title: string
  poster_path?: string | null
}

export async function createRequest(body: CreateRequestBody) {
  const { data } = await client.post('/requests', body)
  return data
}

export async function getMyRequests(page = 1, limit = 20, status?: string) {
  const params: Record<string, string | number> = { page, limit }
  if (status) params.status = status
  const { data } = await client.get('/requests', { params })
  return data
}

export async function deleteRequest(id: number) {
  const { data } = await client.delete(`/requests/${id}`)
  return data
}

export async function getAllRequests(
  page = 1,
  limit = 20,
  status?: string,
  sort: string = "priority",
  mediaType?: 'movie' | 'tv' | 'book'
) {
  const params: Record<string, string | number> = { page, limit, sort }
  if (status) params.status = status
  if (mediaType) params.media_type = mediaType
  const { data } = await client.get('/admin/requests', { params })
  return data
}

export interface RequestRecord {
  id: number
  user_id: string
  username: string
  tmdb_id: number
  media_type: string
  title: string
  poster_path?: string | null
  status: string
  admin_note?: string | null
  supporter_count: number
  supporters: string[]
  is_owner: boolean
  user_supporting: boolean
  days_open: number
  priority_score: number
  jellyfin_item_id?: string | null
  watch_url?: string | null
  created_at: string
  updated_at: string
}

export interface DuplicateGroup {
  group_id: string
  media_type: string
  normalized_title: string
  matched_by_title: boolean
  matched_by_tmdb: boolean
  shared_tmdb_ids: number[]
  request_ids: number[]
  total_supporters: number
  requests: RequestRecord[]
}

export interface DuplicateMergeResult {
  target: RequestRecord
  merged_source_ids: number[]
  notifications_created: number
}

export async function getDuplicateRequestGroups(): Promise<DuplicateGroup[]> {
  const { data } = await client.get('/admin/requests/duplicates')
  return data
}

export async function mergeDuplicateRequests(targetRequestId: number, sourceRequestIds: number[]): Promise<DuplicateMergeResult> {
  const { data } = await client.post('/admin/requests/duplicates/merge', {
    target_request_id: targetRequestId,
    source_request_ids: sourceRequestIds,
  })
  return data
}

export async function updateRequest(id: number, status: string, admin_note?: string) {
  const { data } = await client.patch(`/admin/requests/${id}`, { status, admin_note })
  return data
}

export interface BulkStatusResult {
  updated: any[]
  missing: number[]
}

export async function bulkUpdateRequests(requestIds: number[], status: string, admin_note?: string): Promise<BulkStatusResult> {
  const { data } = await client.post('/admin/requests/bulk-status', {
    request_ids: requestIds,
    status,
    admin_note,
  })
  return data
}

export interface AdminStats {
  total: number
  pending: number
  approved: number
  denied: number
  fulfilled: number
  unique_users: number
  open_over_3_days: number
  open_over_7_days: number
  open_over_14_days: number
  oldest_open_days: number
}

export async function getAdminStats(): Promise<AdminStats> {
  const { data } = await client.get('/admin/stats')
  return data
}

export async function getUsers() {
  const { data } = await client.get('/admin/users')
  return data
}

export async function updateUserRole(userId: string, role: string) {
  const { data } = await client.patch(`/admin/users/${userId}`, { role })
  return data
}

export async function getHealthCheck() {
  const { data } = await client.get('/admin/health')
  return data
}

export async function triggerJellyfinScan() {
  const { data } = await client.post('/admin/jellyfin/scan')
  return data
}

export async function getAnalytics() {
  const { data } = await client.get('/admin/analytics')
  return data
}


export async function updateJellyfinLink(id: number, jellyfin_item_id: string | null) {
  const { data } = await client.patch(`/admin/requests/${id}/jellyfin-link`, { jellyfin_item_id })
  return data
}

// --- Comments ---

export interface Comment {
  id: number
  request_id: number
  user_id: string
  username: string
  is_admin: boolean
  body: string
  created_at: string
}

export async function getComments(requestId: number): Promise<Comment[]> {
  const { data } = await client.get(`/requests/${requestId}/comments`)
  return data
}

export async function postComment(requestId: number, body: string): Promise<Comment> {
  const { data } = await client.post(`/requests/${requestId}/comments`, { body })
  return data
}

export async function deleteComment(requestId: number, commentId: number): Promise<void> {
  await client.delete(`/requests/${requestId}/comments/${commentId}`)
}
