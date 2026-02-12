import client from './client'

export interface BacklogCreateBody {
  type: 'bug' | 'feature'
  title: string
  description?: string
}

export async function createReport(body: BacklogCreateBody) {
  const { data } = await client.post('/backlog', body)
  return data
}

export async function getMyReports() {
  const { data } = await client.get('/backlog/mine')
  return data
}

export async function getAllBacklog(page = 1, limit = 500, status?: string, type?: string) {
  const params: Record<string, string | number> = { page, limit }
  if (status) params.status = status
  if (type) params.type = type
  const { data } = await client.get('/backlog', { params })
  return data
}

export async function updateBacklogItem(id: number, updates: { status?: string; priority?: string; admin_note?: string }) {
  const { data } = await client.patch(`/backlog/${id}`, updates)
  return data
}

export async function deleteBacklogItem(id: number) {
  const { data } = await client.delete(`/backlog/${id}`)
  return data
}

export async function getBacklogStats() {
  const { data } = await client.get('/backlog/stats')
  return data
}
