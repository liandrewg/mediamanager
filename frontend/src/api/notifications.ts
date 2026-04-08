import client from './client'

export interface NotificationRecord {
  id: number
  request_id: number
  user_id: string
  type: string
  message: string
  actor_user_id?: string | null
  actor_name?: string | null
  is_read: boolean
  created_at: string
}

export interface NotificationSummary {
  total: number
  unread: number
  by_type: Record<string, number>
}

export async function getNotifications(): Promise<NotificationRecord[]> {
  const { data } = await client.get('/notifications')
  return data
}

export async function getNotificationSummary(): Promise<NotificationSummary> {
  const { data } = await client.get('/notifications/summary')
  return data
}

export async function markNotificationRead(notificationId: number) {
  const { data } = await client.post(`/notifications/${notificationId}/read`)
  return data
}

export async function markAllNotificationsRead() {
  const { data } = await client.post('/notifications/read-all')
  return data
}
