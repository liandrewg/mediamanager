import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getNotifications,
  getNotificationSummary,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationRecord,
} from '../api/notifications'

type Filter = 'all' | 'unread' | 'read'

const TYPE_LABELS: Record<string, string> = {
  status_changed: 'Status changes',
  comment: 'Comments',
  new_supporter: 'New supporters',
  request_merged: 'Merged requests',
  sla_escalated: 'SLA escalations',
}

function formatRelativeDate(value: string) {
  const date = new Date(value)
  const deltaMs = Date.now() - date.getTime()
  const deltaHours = Math.floor(deltaMs / (1000 * 60 * 60))
  if (deltaHours < 1) return 'Just now'
  if (deltaHours < 24) return `${deltaHours}h ago`
  const deltaDays = Math.floor(deltaHours / 24)
  if (deltaDays < 7) return `${deltaDays}d ago`
  return date.toLocaleDateString()
}

function NotificationTypePill({ type }: { type: string }) {
  return (
    <span className="rounded-full bg-slate-700 px-2 py-1 text-[11px] font-medium text-slate-300">
      {TYPE_LABELS[type] || type.replace(/_/g, ' ')}
    </span>
  )
}

function NotificationRow({
  notification,
  onMarkRead,
}: {
  notification: NotificationRecord
  onMarkRead: (id: number) => void
}) {
  return (
    <div
      className={`rounded-xl border px-4 py-4 ${
        notification.is_read ? 'border-slate-800 bg-slate-900/50' : 'border-blue-500/30 bg-blue-500/10'
      }`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            {!notification.is_read && <span className="h-2.5 w-2.5 rounded-full bg-blue-400" />}
            <NotificationTypePill type={notification.type} />
            <span className="text-xs text-slate-500">{formatRelativeDate(notification.created_at)}</span>
          </div>
          <p className="text-sm text-white">{notification.message}</p>
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
            <span>Request #{notification.request_id}</span>
            {notification.actor_name && <span>From {notification.actor_name}</span>}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Link
            to={`/my-requests#request-${notification.request_id}`}
            className="rounded-lg bg-slate-800 px-3 py-2 text-xs font-medium text-slate-200 transition-colors hover:bg-slate-700"
          >
            View request
          </Link>
          {!notification.is_read && (
            <button
              onClick={() => onMarkRead(notification.id)}
              className="rounded-lg bg-blue-600 px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-blue-700"
            >
              Mark read
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default function NotificationsPage() {
  const [filter, setFilter] = useState<Filter>('unread')
  const queryClient = useQueryClient()

  const { data: notifications = [], isLoading } = useQuery({
    queryKey: ['notifications'],
    queryFn: getNotifications,
  })

  const { data: summary } = useQuery({
    queryKey: ['notificationSummary'],
    queryFn: getNotificationSummary,
  })

  const markReadMutation = useMutation({
    mutationFn: markNotificationRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      queryClient.invalidateQueries({ queryKey: ['notificationSummary'] })
    },
  })

  const markAllMutation = useMutation({
    mutationFn: markAllNotificationsRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      queryClient.invalidateQueries({ queryKey: ['notificationSummary'] })
    },
  })

  const filteredNotifications = useMemo(() => {
    if (filter === 'unread') return notifications.filter((item) => !item.is_read)
    if (filter === 'read') return notifications.filter((item) => item.is_read)
    return notifications
  }, [filter, notifications])

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Updates</h2>
          <p className="mt-1 text-sm text-slate-400">A single inbox for request status changes, comments, merges, and queue movement.</p>
        </div>
        <button
          onClick={() => markAllMutation.mutate()}
          disabled={(summary?.unread || 0) === 0 || markAllMutation.isPending}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
        >
          {markAllMutation.isPending ? 'Marking...' : 'Mark all read'}
        </button>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
          <p className="text-sm text-slate-400">Unread</p>
          <p className="mt-2 text-3xl font-semibold text-white">{summary?.unread || 0}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
          <p className="text-sm text-slate-400">Total updates</p>
          <p className="mt-2 text-3xl font-semibold text-white">{summary?.total || 0}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
          <p className="text-sm text-slate-400">Top unread type</p>
          <p className="mt-2 text-lg font-semibold text-white">
            {summary && Object.keys(summary.by_type).length > 0
              ? TYPE_LABELS[
                  Object.entries(summary.by_type).sort((a, b) => b[1] - a[1])[0][0]
                ] || Object.entries(summary.by_type).sort((a, b) => b[1] - a[1])[0][0]
              : 'No unread updates'}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {(['unread', 'all', 'read'] as Filter[]).map((value) => (
          <button
            key={value}
            onClick={() => setFilter(value)}
            className={`rounded-lg px-3 py-1.5 text-sm transition-colors ${
              filter === value ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            {value[0].toUpperCase() + value.slice(1)}
          </button>
        ))}
      </div>

      {isLoading ? <p className="text-slate-400">Loading updates...</p> : null}

      {!isLoading && filteredNotifications.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900/40 px-6 py-12 text-center">
          <p className="font-medium text-white">No {filter === 'all' ? '' : filter} updates.</p>
          <p className="mt-2 text-sm text-slate-500">When request activity happens, it will land here instead of turning into DM chaos.</p>
        </div>
      )}

      <div className="space-y-3">
        {filteredNotifications.map((notification) => (
          <NotificationRow
            key={notification.id}
            notification={notification}
            onMarkRead={(id) => markReadMutation.mutate(id)}
          />
        ))}
      </div>
    </div>
  )
}
