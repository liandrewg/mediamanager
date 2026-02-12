import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getAllRequests, updateRequest, getAdminStats } from '../api/requests'
import RequestBadge from '../components/RequestBadge'
import StatsCard from '../components/StatsCard'

export default function AdminPage() {
  const [statusFilter, setStatusFilter] = useState<string>('pending')
  const queryClient = useQueryClient()

  const { data: stats } = useQuery({
    queryKey: ['adminStats'],
    queryFn: getAdminStats,
  })

  const { data, isLoading } = useQuery({
    queryKey: ['adminRequests', statusFilter],
    queryFn: () => getAllRequests(1, 100, statusFilter || undefined),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, status, note }: { id: number; status: string; note?: string }) =>
      updateRequest(id, status, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adminRequests'] })
      queryClient.invalidateQueries({ queryKey: ['adminStats'] })
    },
  })

  const requests = data?.items || []

  return (
    <div>
      <h2 className="text-2xl font-bold text-white mb-6">Admin Panel</h2>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
          <StatsCard label="Total Requests" value={stats.total} />
          <StatsCard label="Pending" value={stats.pending} />
          <StatsCard label="Approved" value={stats.approved} />
          <StatsCard label="Fulfilled" value={stats.fulfilled} />
          <StatsCard label="Unique Users" value={stats.unique_users} />
        </div>
      )}

      <div className="flex gap-2 mb-6">
        {['', 'pending', 'approved', 'denied', 'fulfilled'].map((s) => (
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
        <p className="text-slate-500 text-center py-12">No requests found.</p>
      )}

      {!isLoading && requests.length > 0 && (
        <div className="bg-slate-800 rounded-lg overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-700">
                <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Title</th>
                <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Type</th>
                <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">User</th>
                <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Status</th>
                <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Date</th>
                <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {requests.map((req: any) => (
                <tr key={req.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                  <td className="px-4 py-3 text-white text-sm">{req.title}</td>
                  <td className="px-4 py-3 text-slate-400 text-sm uppercase">{req.media_type}</td>
                  <td className="px-4 py-3 text-slate-300 text-sm">{req.username}</td>
                  <td className="px-4 py-3">
                    <RequestBadge status={req.status} />
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-sm">
                    {new Date(req.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      {req.status === 'pending' && (
                        <>
                          <button
                            onClick={() => updateMutation.mutate({ id: req.id, status: 'approved' })}
                            className="text-green-400 hover:text-green-300 text-sm"
                          >
                            Approve
                          </button>
                          <button
                            onClick={() => updateMutation.mutate({ id: req.id, status: 'denied' })}
                            className="text-red-400 hover:text-red-300 text-sm"
                          >
                            Deny
                          </button>
                        </>
                      )}
                      {req.status === 'approved' && (
                        <button
                          onClick={() => updateMutation.mutate({ id: req.id, status: 'fulfilled' })}
                          className="text-blue-400 hover:text-blue-300 text-sm"
                        >
                          Mark Fulfilled
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
