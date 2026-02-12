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

export async function getAllRequests(page = 1, limit = 20, status?: string) {
  const params: Record<string, string | number> = { page, limit }
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
