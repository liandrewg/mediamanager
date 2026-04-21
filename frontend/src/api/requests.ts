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

export interface HouseholdQueueResponse {
  items: RequestRecord[]
  total: number
  page: number
  limit: number
  total_pages: number
  summary: {
    total: number
    pending: number
    approved: number
    open_total: number
    total_supporters: number
  }
}

export async function getHouseholdQueue(options?: {
  page?: number
  limit?: number
  status?: 'open' | 'all' | 'pending' | 'approved' | 'fulfilled' | 'denied'
  mediaType?: 'movie' | 'tv' | 'book'
  sort?: 'priority' | 'supporters' | 'newest' | 'oldest'
  query?: string
}): Promise<HouseholdQueueResponse> {
  const params: Record<string, string | number> = {
    page: options?.page ?? 1,
    limit: options?.limit ?? 20,
    status: options?.status ?? 'open',
    sort: options?.sort ?? 'priority',
  }
  if (options?.mediaType) params.media_type = options.mediaType
  if (options?.query) params.q = options.query
  const { data } = await client.get('/requests/household', { params })
  return data
}

export async function deleteRequest(id: number) {
  const { data } = await client.delete(`/requests/${id}`)
  return data
}

export interface RequestTimelineEvent {
  id: string
  event_type: string
  title: string
  description?: string | null
  actor_name?: string | null
  created_at: string
}

export async function getRequestTimeline(requestId: number): Promise<RequestTimelineEvent[]> {
  const { data } = await client.get(`/requests/${requestId}/timeline`)
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
  queue_position?: number | null
  queue_size?: number | null
  queue_ahead_count?: number | null
  approved_ahead_count?: number | null
  pending_ahead_count?: number | null
  supporters_ahead_count?: number | null
  queue_band?: 'up_next' | 'near_front' | 'in_pack' | 'long_tail' | null
  queue_reason?: string | null
  blocker_label?: string | null
  next_step_label?: string | null
  next_step_by?: string | null
  eta_label?: string | null
  eta_start?: string | null
  eta_end?: string | null
  eta_confidence?: 'low' | 'medium' | 'high' | null
  benchmark_label?: string | null
  benchmark_source?: 'media_type' | 'household' | null
  promise_status?: 'ahead' | 'on_track' | 'at_risk' | 'breached' | 'done' | null
  promise_summary?: string | null
  follow_up_label?: string | null
  follow_up_by?: string | null
  blocker_reason?: string | null
  blocker_note?: string | null
  blocker_review_on?: string | null
  blocker_is_overdue?: boolean
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

export interface AdminReplyPackItem {
  id: number
  title: string
  status: string
  media_type: string
  username: string
  supporter_count: number
  days_open: number
  queue_position?: number | null
  queue_size?: number | null
  promise_status?: string | null
  urgency: 'critical' | 'high' | 'medium'
  reason: string
  queue_reason?: string | null
  next_step_label?: string | null
  next_step_by?: string | null
  follow_up_by?: string | null
  eta_label?: string | null
  suggested_note: string
}

export interface AdminReplyPackResponse {
  summary: {
    critical: number
    high: number
    medium: number
    total: number
  }
  items: AdminReplyPackItem[]
}

export async function getAdminReplyPack(limit = 8): Promise<AdminReplyPackResponse> {
  const { data } = await client.get('/admin/reply-pack', { params: { limit } })
  return data
}

export interface RequesterDigestPackItemRequest {
  id: number
  title: string
  status: string
  media_type: string
  supporter_count: number
  days_open: number
  queue_position?: number | null
  queue_size?: number | null
  next_step_label?: string | null
  next_step_by?: string | null
  eta_label?: string | null
  promise_status?: string | null
}

export interface RequesterDigestPackItem {
  user_id: string
  username: string
  urgency: 'critical' | 'high' | 'medium'
  reason: string
  open_request_count: number
  breached_count: number
  at_risk_count: number
  approved_count: number
  pending_count: number
  total_supporters: number
  request_titles: string[]
  requests: RequesterDigestPackItemRequest[]
  suggested_note: string
}

export interface RequesterDigestPackResponse {
  summary: {
    critical: number
    high: number
    medium: number
    total: number
  }
  items: RequesterDigestPackItem[]
}

export async function getRequesterDigestPack(limit = 6): Promise<RequesterDigestPackResponse> {
  const { data } = await client.get('/admin/requester-digest-pack', { params: { limit } })
  return data
}

export interface RequestReviewLoopItem {
  request_id: number
  title: string
  media_type: string
  status: string
  username: string
  supporter_count: number
  days_open: number
  reason: string
  note?: string | null
  review_on: string
  lane: 'overdue' | 'today' | 'upcoming'
  is_overdue: boolean
}

export interface RequestReviewLoopResponse {
  summary: {
    overdue: number
    today: number
    upcoming: number
    total: number
  }
  items: RequestReviewLoopItem[]
}

export async function getRequestReviewLoop(limit = 8): Promise<RequestReviewLoopResponse> {
  const { data } = await client.get('/admin/review-loop', { params: { limit } })
  return data
}

export async function setRequestBlocker(id: number, body: { reason: string; review_on: string; note?: string }) {
  const { data } = await client.put(`/admin/requests/${id}/blocker`, body)
  return data
}

export async function clearRequestBlocker(id: number) {
  const { data } = await client.delete(`/admin/requests/${id}/blocker`)
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

export interface AdminAnalytics {
  total_requests_all_time: number
  fulfilled_all_time: number
  fulfillment_rate: number
  avg_lead_time_days: number | null
  median_lead_time_days: number | null
  p90_lead_time_days: number | null
  sla_days: number
  fulfilled_within_sla_count: number
  fulfilled_outside_sla_count: number
  fulfilled_within_sla_rate: number
  recommended_sla_days: number | null
  recommended_sla_within_rate: number | null
  recommended_sla_sample_size: number
  open_count: number
  pending_count: number
  approved_count: number
  denied_count: number
  escalated_count: number
  oldest_open_days: number
  open_breaching_sla: number
  open_breaching_recommended_sla: number | null
  open_due_soon: number
  media_type_sla_insights: {
    media_type: string
    fulfilled_sample_size: number
    median_lead_time_days: number | null
    recommended_target_days: number | null
    recommended_within_rate: number | null
    open_count: number
    open_breaching_global_policy: number
    open_breaching_recommended: number | null
  }[]
  top_requesters: { username: string; count: number }[]
  by_media_type: { media_type: string; total: number; fulfilled: number }[]
  monthly_volume: { month: string; submitted: number; fulfilled: number }[]
  weekly_throughput: { week: string; fulfilled: number }[]
  weekly_sla_hit_rate: {
    week: string
    within_sla: number
    fulfilled: number
    hit_rate: number
  }[]
  sla_trend_delta: number
  sla_trend_direction: 'improving' | 'flat' | 'regressing'
  sla_policy_advisor: {
    recommended_action: 'tighten' | 'hold' | 'relax'
    suggested_target_days: number | null
    confidence: 'low' | 'medium' | 'high'
    summary: string
    reasons: string[]
    review_trigger: string
    sample_size: number
  }
  total_supporters_ever: number
  avg_supporters_per_request: number
}

export async function getAnalytics(): Promise<AdminAnalytics> {
  const { data } = await client.get('/admin/analytics')
  return data
}

export async function applyRecommendedSlaPolicy(warning_days_override?: number): Promise<SlaPolicy> {
  const body = warning_days_override === undefined ? {} : { warning_days_override }
  const { data } = await client.post('/admin/sla-policy/apply-recommended', body)
  return data
}

export interface SlaSimulationScenarioDelta {
  open_breaching: number
  open_due_soon: number
  historical_hit_rate: number | null
  operational_risk_score: number
}

export interface SlaSimulationScenario {
  target_days: number
  warning_days: number
  historical_hit_rate: number | null
  historical_within_count: number
  historical_sample_size: number
  open_breaching: number
  open_due_soon: number
  operational_risk_score: number
  delta_vs_current: SlaSimulationScenarioDelta | null
  is_recommended: boolean
}

export interface SlaSimulationResponse {
  scenarios: SlaSimulationScenario[]
  open_sample_size: number
  historical_sample_size: number
  current_target_days: number | null
  recommended_target_days: number | null
}

export async function simulateSlaPolicy(targetDays: number[]): Promise<SlaSimulationResponse> {
  const targets = targetDays.join(',')
  const { data } = await client.get('/admin/sla-policy/simulate', { params: { targets } })
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


export interface SlaPolicy {
  target_days: number
  warning_days: number
  updated_at?: string | null
}

export interface SlaWorklistResponse {
  policy: SlaPolicy
  summary: {
    breached: number
    due_soon: number
    on_track: number
    total_open: number
  }
  state: 'all' | 'breached' | 'due_soon' | 'on_track'
  items: (RequestRecord & {
    sla_target_days: number
    sla_warning_days: number
    days_until_breach: number
    sla_state: 'breached' | 'due_soon' | 'on_track'
  })[]
}

export async function getSlaPolicy(): Promise<SlaPolicy> {
  const { data } = await client.get('/admin/sla-policy')
  return data
}

export async function updateSlaPolicy(target_days: number, warning_days: number): Promise<SlaPolicy> {
  const { data } = await client.patch('/admin/sla-policy', { target_days, warning_days })
  return data
}

export async function getSlaWorklist(state: 'all' | 'breached' | 'due_soon' | 'on_track' = 'all'): Promise<SlaWorklistResponse> {
  const { data } = await client.get('/admin/sla-worklist', { params: { state, limit: 500 } })
  return data
}

export async function bulkEscalateSlaRequests(requestIds: number[], note?: string): Promise<BulkStatusResult> {
  const { data } = await client.post('/admin/sla-worklist/escalate', {
    request_ids: requestIds,
    note,
  })
  return data
}
