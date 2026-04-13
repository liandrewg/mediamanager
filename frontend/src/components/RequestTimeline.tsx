import { useQuery } from '@tanstack/react-query'
import { getRequestTimeline, type RequestTimelineEvent } from '../api/requests'

interface Props {
  requestId: number
}

function formatDate(iso: string) {
  const value = new Date(iso + (iso.endsWith('Z') ? '' : 'Z'))
  return value.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function eventTone(eventType: string) {
  switch (eventType) {
    case 'request_submitted':
      return 'bg-cyan-500'
    case 'supporter_joined':
      return 'bg-violet-500'
    case 'status_changed':
      return 'bg-emerald-500'
    default:
      return 'bg-amber-500'
  }
}

export default function RequestTimeline({ requestId }: Props) {
  const { data: events = [], isLoading } = useQuery<RequestTimelineEvent[]>({
    queryKey: ['requestTimeline', requestId],
    queryFn: () => getRequestTimeline(requestId),
  })

  return (
    <div className="mt-4 border-t border-slate-700 pt-4">
      <h4 className="text-sm font-semibold text-slate-400 mb-3 flex items-center gap-2">
        <span>🕒</span>
        <span>Timeline {events.length > 0 && `(${events.length})`}</span>
      </h4>

      {isLoading && <p className="text-xs text-slate-500 italic">Loading timeline…</p>}

      {!isLoading && events.length === 0 && (
        <p className="text-xs text-slate-500 italic">No timeline events yet.</p>
      )}

      {events.length > 0 && (
        <div className="space-y-3">
          {events.map((event, index) => (
            <div key={event.id} className="flex gap-3">
              <div className="flex flex-col items-center">
                <span className={`mt-1 h-2.5 w-2.5 rounded-full ${eventTone(event.event_type)}`} />
                {index < events.length - 1 && <span className="mt-1 w-px flex-1 bg-slate-700" />}
              </div>
              <div className="flex-1 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium text-slate-100">{event.title}</p>
                  <span className="text-[11px] text-slate-500">{formatDate(event.created_at)}</span>
                </div>
                {event.actor_name && (
                  <p className="mt-1 text-[11px] uppercase tracking-wide text-slate-500">{event.actor_name}</p>
                )}
                {event.description && (
                  <p className="mt-1 text-sm text-slate-300 whitespace-pre-wrap">{event.description}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
