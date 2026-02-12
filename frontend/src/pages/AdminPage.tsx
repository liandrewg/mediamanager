import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getAllRequests, updateRequest, getAdminStats, getUsers, updateUserRole } from '../api/requests'
import { useAuth } from '../context/AuthContext'
import RequestBadge from '../components/RequestBadge'
import StatsCard from '../components/StatsCard'

const COLUMNS = [
  { key: 'pending', label: 'Pending', color: 'border-yellow-500', bg: 'bg-yellow-500/10' },
  { key: 'approved', label: 'Approved', color: 'border-blue-500', bg: 'bg-blue-500/10' },
  { key: 'fulfilled', label: 'Fulfilled', color: 'border-green-500', bg: 'bg-green-500/10' },
  { key: 'denied', label: 'Denied', color: 'border-red-500', bg: 'bg-red-500/10' },
]

const TRANSITIONS: Record<string, { label: string; status: string; style: string }[]> = {
  pending: [
    { label: 'Approve', status: 'approved', style: 'bg-blue-600 hover:bg-blue-700 text-white' },
    { label: 'Deny', status: 'denied', style: 'bg-red-600 hover:bg-red-700 text-white' },
  ],
  approved: [
    { label: 'Mark Fulfilled', status: 'fulfilled', style: 'bg-green-600 hover:bg-green-700 text-white' },
    { label: 'Back to Pending', status: 'pending', style: 'bg-yellow-600 hover:bg-yellow-700 text-white' },
    { label: 'Deny', status: 'denied', style: 'bg-red-600 hover:bg-red-700 text-white' },
  ],
  fulfilled: [
    { label: 'Reopen', status: 'approved', style: 'bg-slate-600 hover:bg-slate-500 text-white' },
  ],
  denied: [
    { label: 'Reopen', status: 'pending', style: 'bg-yellow-600 hover:bg-yellow-700 text-white' },
  ],
}

type Tab = 'requests' | 'users'

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>('requests')
  const [view, setView] = useState<'board' | 'table'>('board')
  const [noteModal, setNoteModal] = useState<{ id: number; status: string } | null>(null)
  const [noteText, setNoteText] = useState('')
  const queryClient = useQueryClient()
  const { user: currentUser } = useAuth()

  const { data: stats } = useQuery({
    queryKey: ['adminStats'],
    queryFn: getAdminStats,
  })

  const { data, isLoading } = useQuery({
    queryKey: ['adminRequests', ''],
    queryFn: () => getAllRequests(1, 500),
    enabled: tab === 'requests',
  })

  const { data: users, isLoading: usersLoading } = useQuery({
    queryKey: ['adminUsers'],
    queryFn: getUsers,
    enabled: tab === 'users',
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, status, note }: { id: number; status: string; note?: string }) =>
      updateRequest(id, status, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adminRequests'] })
      queryClient.invalidateQueries({ queryKey: ['adminStats'] })
    },
  })

  const roleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      updateUserRole(userId, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adminUsers'] })
    },
  })

  const allRequests: any[] = data?.items || []

  const handleMove = (id: number, status: string) => {
    setNoteModal({ id, status })
    setNoteText('')
  }

  const confirmMove = () => {
    if (noteModal) {
      updateMutation.mutate({ id: noteModal.id, status: noteModal.status, note: noteText || undefined })
      setNoteModal(null)
      setNoteText('')
    }
  }

  const quickMove = (id: number, status: string) => {
    updateMutation.mutate({ id, status })
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-white">Admin Panel</h2>
        <div className="flex gap-2">
          {tab === 'requests' && (
            <>
              <button
                onClick={() => setView('board')}
                className={`px-3 py-1.5 rounded text-sm transition-colors ${
                  view === 'board' ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                }`}
              >
                Board
              </button>
              <button
                onClick={() => setView('table')}
                className={`px-3 py-1.5 rounded text-sm transition-colors ${
                  view === 'table' ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                }`}
              >
                Table
              </button>
            </>
          )}
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-1 mb-6 border-b border-slate-700">
        <button
          onClick={() => setTab('requests')}
          className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px ${
            tab === 'requests'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-white'
          }`}
        >
          Requests
        </button>
        <button
          onClick={() => setTab('users')}
          className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px ${
            tab === 'users'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-white'
          }`}
        >
          Users & Permissions
        </button>
      </div>

      {/* ========== REQUESTS TAB ========== */}
      {tab === 'requests' && (
        <>
          {stats && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
              <StatsCard label="Total Requests" value={stats.total} />
              <StatsCard label="Pending" value={stats.pending} />
              <StatsCard label="Approved" value={stats.approved} />
              <StatsCard label="Fulfilled" value={stats.fulfilled} />
              <StatsCard label="Unique Users" value={stats.unique_users} />
            </div>
          )}

          {isLoading && <p className="text-slate-400">Loading...</p>}

          {/* Board View */}
          {!isLoading && view === 'board' && (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
              {COLUMNS.map((col) => {
                const items = allRequests.filter((r) => r.status === col.key)
                const transitions = TRANSITIONS[col.key] || []
                return (
                  <div key={col.key} className={`rounded-lg border-t-2 ${col.color} ${col.bg}`}>
                    <div className="p-4 border-b border-slate-700/50">
                      <div className="flex items-center justify-between">
                        <h3 className="font-semibold text-white">{col.label}</h3>
                        <span className="text-xs bg-slate-700 text-slate-300 px-2 py-0.5 rounded-full">
                          {items.length}
                        </span>
                      </div>
                    </div>
                    <div className="p-2 space-y-2 max-h-[calc(100vh-340px)] overflow-y-auto">
                      {items.length === 0 && (
                        <p className="text-slate-500 text-xs text-center py-6">No requests</p>
                      )}
                      {items.map((req: any) => (
                        <div key={req.id} className="bg-slate-800 rounded-lg p-3 space-y-2">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className="text-sm font-medium text-white truncate">{req.title}</p>
                              <p className="text-xs text-slate-400">
                                {req.username} &middot; {req.media_type.toUpperCase()} &middot;{' '}
                                {new Date(req.created_at).toLocaleDateString()}
                              </p>
                            </div>
                          </div>
                          {req.admin_note && (
                            <p className="text-xs text-slate-400 italic border-l-2 border-slate-600 pl-2">
                              {req.admin_note}
                            </p>
                          )}
                          {transitions.length > 0 && (
                            <div className="flex flex-wrap gap-1.5 pt-1">
                              {transitions.map((t) => (
                                <button
                                  key={t.status}
                                  onClick={() => handleMove(req.id, t.status)}
                                  disabled={updateMutation.isPending}
                                  className={`px-2 py-1 rounded text-xs font-medium transition-colors disabled:opacity-50 ${t.style}`}
                                >
                                  {t.label}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {/* Table View */}
          {!isLoading && view === 'table' && (
            <div className="bg-slate-800 rounded-lg overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Title</th>
                    <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Type</th>
                    <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">User</th>
                    <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Status</th>
                    <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Date</th>
                    <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Note</th>
                    <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Move to</th>
                  </tr>
                </thead>
                <tbody>
                  {allRequests.map((req: any) => {
                    const transitions = TRANSITIONS[req.status] || []
                    return (
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
                        <td className="px-4 py-3 text-slate-400 text-sm max-w-48 truncate">
                          {req.admin_note || '-'}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex gap-1.5">
                            {transitions.map((t) => (
                              <button
                                key={t.status}
                                onClick={() => quickMove(req.id, t.status)}
                                disabled={updateMutation.isPending}
                                className={`px-2 py-1 rounded text-xs font-medium transition-colors disabled:opacity-50 ${t.style}`}
                              >
                                {t.label}
                              </button>
                            ))}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* ========== USERS TAB ========== */}
      {tab === 'users' && (
        <div>
          <p className="text-slate-400 text-sm mb-6">
            Manage user roles. Admins can manage requests and other users. Users who have logged in at least once appear here.
          </p>

          {usersLoading && <p className="text-slate-400">Loading...</p>}

          {!usersLoading && users && users.length === 0 && (
            <p className="text-slate-500 text-center py-12">No users have logged in yet.</p>
          )}

          {!usersLoading && users && users.length > 0 && (
            <div className="bg-slate-800 rounded-lg overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Username</th>
                    <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Role</th>
                    <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">First Login</th>
                    <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Last Updated</th>
                    <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u: any) => {
                    const isSelf = u.user_id === currentUser?.id
                    return (
                      <tr key={u.user_id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                        <td className="px-4 py-3 text-white text-sm">
                          {u.username}
                          {isSelf && (
                            <span className="ml-2 text-xs text-slate-500">(you)</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`text-xs px-2 py-1 rounded font-medium ${
                              u.role === 'admin'
                                ? 'bg-purple-600/30 text-purple-300'
                                : 'bg-slate-600/30 text-slate-300'
                            }`}
                          >
                            {u.role}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-slate-400 text-sm">
                          {new Date(u.created_at).toLocaleDateString()}
                        </td>
                        <td className="px-4 py-3 text-slate-400 text-sm">
                          {new Date(u.updated_at).toLocaleDateString()}
                        </td>
                        <td className="px-4 py-3">
                          {isSelf ? (
                            <span className="text-xs text-slate-500">-</span>
                          ) : u.role === 'user' ? (
                            <button
                              onClick={() => roleMutation.mutate({ userId: u.user_id, role: 'admin' })}
                              disabled={roleMutation.isPending}
                              className="bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white px-3 py-1 rounded text-xs font-medium transition-colors"
                            >
                              Promote to Admin
                            </button>
                          ) : (
                            <button
                              onClick={() => roleMutation.mutate({ userId: u.user_id, role: 'user' })}
                              disabled={roleMutation.isPending}
                              className="bg-slate-600 hover:bg-slate-500 disabled:opacity-50 text-white px-3 py-1 rounded text-xs font-medium transition-colors"
                            >
                              Demote to User
                            </button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          {roleMutation.isError && (
            <p className="text-red-400 text-sm mt-4">
              {(roleMutation.error as any)?.response?.data?.detail || 'Failed to update role'}
            </p>
          )}
        </div>
      )}

      {/* Note Modal */}
      {noteModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-xl p-6 w-full max-w-md shadow-xl">
            <h3 className="text-lg font-semibold text-white mb-1">Move Request</h3>
            <p className="text-sm text-slate-400 mb-4">
              Changing status to <span className="font-medium text-white capitalize">{noteModal.status}</span>. Add an optional note:
            </p>
            <textarea
              value={noteText}
              onChange={(e) => setNoteText(e.target.value)}
              placeholder="Optional note for the user..."
              rows={3}
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            />
            <div className="flex justify-end gap-3 mt-4">
              <button
                onClick={() => setNoteModal(null)}
                className="px-4 py-2 text-sm text-slate-300 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmMove}
                disabled={updateMutation.isPending}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 text-white text-sm rounded-lg font-medium transition-colors"
              >
                {updateMutation.isPending ? 'Updating...' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
