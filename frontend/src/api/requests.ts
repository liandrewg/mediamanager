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

export async function getAllRequests(page = 1, limit = 20, status?: string, sort: string = "priority") {
  const params: Record<string, string | number> = { page, limit, sort }
  if (status) params.status = status
  const { data } = await client.get('/admin/requests', { params })
  return data
}

export async function updateRequest(id: number, status: string, admin_note?: string) {
  const { data } = await client.patch(`/admin/requests/${id}`, { status, admin_note })
  return data
}

export async function getAdminStats() {
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
