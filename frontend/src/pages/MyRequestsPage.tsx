import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getMyRequests, deleteRequest } from '../api/requests'
import RequestBadge from '../components/RequestBadge'

export default function MyRequestsPage() {
  const [statusFilter, setStatusFilter] = useState<string>('')
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['myRequests', statusFilter],
    queryFn: () => getMyRequests(1, 100, statusFilter || undefined),
  })

  const cancelMutation = useMutation({
    mutationFn: (id: number) => deleteRequest(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['myRequests'] }),
  })

  const requests = data?.items || []

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-white">My Requests</h2>
        <Link
          to="/search"
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          + New Request
        </Link>
      </div>

      <div className="flex flex-wrap gap-2 mb-6">
        {['', 'pending', 'approved', 'fulfilled', 'denied'].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1.5 rounded text-sm transition-colors ${
              statusFilter === s
                ? 'bg-blue-600 text-white'
                : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            {s || 'All'}
          </button>
        ))}
      </div>

      {isLoading && <p className="text-slate-400">Loading...</p>}

      {!isLoading && requests.length === 0 && (
        <p className="text-slate-500 text-center py-12">No requests yet. Search for media to make a request.</p>
      )}

      {/* Mobile card view */}
      {!isLoading && requests.length > 0 && (
        <div className="md:hidden space-y-3">
          {requests.map((req: any) => (
            <div key={req.id} className="bg-slate-800 rounded-lg p-4 space-y-2">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm font-medium text-white">{req.title}</p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {req.media_type.toUpperCase()} &middot; {new Date(req.created_at).toLocaleDateString()}
                  </p>
                </div>
                <RequestBadge status={req.status} />
              </div>
              {req.admin_note && (
                <p className="text-xs text-slate-400 italic border-l-2 border-slate-600 pl-2">{req.admin_note}</p>
              )}
              {req.status === 'pending' && (
                <button
                  onClick={() => cancelMutation.mutate(req.id)}
                  className="text-red-400 hover:text-red-300 text-sm"
                >
                  Cancel
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Desktop table view */}
      {!isLoading && requests.length > 0 && (
        <div className="hidden md:block bg-slate-800 rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Title</th>
                  <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Type</th>
                  <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Status</th>
                  <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Date</th>
                  <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Note</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {requests.map((req: any) => (
                  <tr key={req.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                    <td className="px-4 py-3 text-white text-sm">{req.title}</td>
                    <td className="px-4 py-3 text-slate-400 text-sm uppercase">{req.media_type}</td>
                    <td className="px-4 py-3">
                      <RequestBadge status={req.status} />
                    </td>
                    <td className="px-4 py-3 text-slate-400 text-sm">
                      {new Date(req.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-slate-400 text-sm">{req.admin_note || '-'}</td>
                    <td className="px-4 py-3">
                      {req.status === 'pending' && (
                        <button
                          onClick={() => cancelMutation.mutate(req.id)}
                          className="text-red-400 hover:text-red-300 text-sm"
                        >
                          Cancel
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
