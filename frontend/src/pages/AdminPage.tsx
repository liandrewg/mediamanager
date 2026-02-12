import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getAllRequests, updateRequest, getAdminStats, getUsers, updateUserRole, getHealthCheck, triggerJellyfinScan } from '../api/requests'
import { getAllBacklog, updateBacklogItem, deleteBacklogItem, getBacklogStats } from '../api/backlog'
import { getTunnelStatus, startTunnel, stopTunnel } from '../api/tunnel'
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

const BACKLOG_COLUMNS = [
  { key: 'reported', label: 'Reported', color: 'border-yellow-500', bg: 'bg-yellow-500/10' },
  { key: 'triaged', label: 'Triaged', color: 'border-blue-500', bg: 'bg-blue-500/10' },
  { key: 'in_progress', label: 'In Progress', color: 'border-purple-500', bg: 'bg-purple-500/10' },
  { key: 'ready_for_test', label: 'Ready for Test', color: 'border-cyan-500', bg: 'bg-cyan-500/10' },
  { key: 'resolved', label: 'Resolved', color: 'border-green-500', bg: 'bg-green-500/10' },
  { key: 'wont_fix', label: "Won't Fix", color: 'border-slate-500', bg: 'bg-slate-500/10' },
]

const BACKLOG_TRANSITIONS: Record<string, { label: string; status: string; style: string }[]> = {
  reported: [
    { label: 'Triage', status: 'triaged', style: 'bg-blue-600 hover:bg-blue-700 text-white' },
    { label: "Won't Fix", status: 'wont_fix', style: 'bg-slate-600 hover:bg-slate-500 text-white' },
  ],
  triaged: [
    { label: 'Start Work', status: 'in_progress', style: 'bg-purple-600 hover:bg-purple-700 text-white' },
    { label: "Won't Fix", status: 'wont_fix', style: 'bg-slate-600 hover:bg-slate-500 text-white' },
  ],
  in_progress: [
    { label: 'Ready for Test', status: 'ready_for_test', style: 'bg-cyan-600 hover:bg-cyan-700 text-white' },
    { label: 'Back to Triaged', status: 'triaged', style: 'bg-blue-600 hover:bg-blue-700 text-white' },
  ],
  ready_for_test: [
    { label: 'Resolve', status: 'resolved', style: 'bg-green-600 hover:bg-green-700 text-white' },
    { label: 'Back to In Progress', status: 'in_progress', style: 'bg-purple-600 hover:bg-purple-700 text-white' },
  ],
  resolved: [
    { label: 'Reopen', status: 'triaged', style: 'bg-blue-600 hover:bg-blue-700 text-white' },
  ],
  wont_fix: [
    { label: 'Reopen', status: 'reported', style: 'bg-yellow-600 hover:bg-yellow-700 text-white' },
  ],
}

const PRIORITY_STYLES: Record<string, string> = {
  low: 'bg-slate-600/30 text-slate-300',
  medium: 'bg-yellow-600/30 text-yellow-300',
  high: 'bg-orange-600/30 text-orange-300',
  critical: 'bg-red-600/30 text-red-300',
}

type Tab = 'requests' | 'backlog' | 'users' | 'tunnel' | 'health'

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

  const { data: blStats } = useQuery({
    queryKey: ['backlogStats'],
    queryFn: getBacklogStats,
    enabled: tab === 'backlog',
  })

  const { data: backlogData, isLoading: backlogLoading } = useQuery({
    queryKey: ['adminBacklog'],
    queryFn: () => getAllBacklog(),
    enabled: tab === 'backlog',
  })

  const backlogMutation = useMutation({
    mutationFn: ({ id, ...updates }: { id: number; status?: string; priority?: string; admin_note?: string }) =>
      updateBacklogItem(id, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adminBacklog'] })
      queryClient.invalidateQueries({ queryKey: ['backlogStats'] })
    },
  })

  const backlogDeleteMutation = useMutation({
    mutationFn: (id: number) => deleteBacklogItem(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adminBacklog'] })
      queryClient.invalidateQueries({ queryKey: ['backlogStats'] })
    },
  })

  const allBacklog: any[] = backlogData?.items || []

  const [blNoteModal, setBlNoteModal] = useState<{ id: number; status: string } | null>(null)
  const [blNoteText, setBlNoteText] = useState('')

  const handleBacklogMove = (id: number, status: string) => {
    setBlNoteModal({ id, status })
    setBlNoteText('')
  }

  const confirmBacklogMove = () => {
    if (blNoteModal) {
      backlogMutation.mutate({ id: blNoteModal.id, status: blNoteModal.status, admin_note: blNoteText || undefined })
      setBlNoteModal(null)
      setBlNoteText('')
    }
  }

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

  const { data: tunnelData, isLoading: tunnelLoading } = useQuery({
    queryKey: ['tunnelStatus'],
    queryFn: getTunnelStatus,
    enabled: tab === 'tunnel',
    refetchInterval: tab === 'tunnel' ? 10000 : false,
  })

  const startTunnelMutation = useMutation({
    mutationFn: startTunnel,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tunnelStatus'] }),
  })

  const stopTunnelMutation = useMutation({
    mutationFn: stopTunnel,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tunnelStatus'] }),
  })

  const { data: healthData, isLoading: healthLoading, refetch: refetchHealth } = useQuery({
    queryKey: ['healthCheck'],
    queryFn: getHealthCheck,
    enabled: tab === 'health',
    refetchInterval: tab === 'health' ? 30000 : false,
  })

  const scanMutation = useMutation({
    mutationFn: triggerJellyfinScan,
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
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6">
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
      <div className="flex gap-1 mb-6 border-b border-slate-700 overflow-x-auto -mx-4 px-4 md:mx-0 md:px-0">
        <button
          onClick={() => setTab('requests')}
          className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap ${
            tab === 'requests'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-white'
          }`}
        >
          Requests
        </button>
        <button
          onClick={() => setTab('backlog')}
          className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap ${
            tab === 'backlog'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-white'
          }`}
        >
          Backlog
        </button>
        <button
          onClick={() => setTab('users')}
          className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap ${
            tab === 'users'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-white'
          }`}
        >
          Users
        </button>
        <button
          onClick={() => setTab('tunnel')}
          className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap ${
            tab === 'tunnel'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-white'
          }`}
        >
          Tunnel
        </button>
        <button
          onClick={() => setTab('health')}
          className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap ${
            tab === 'health'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-white'
          }`}
        >
          Health
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
            <div className="bg-slate-800 rounded-lg overflow-hidden overflow-x-auto">
              <table className="w-full min-w-[700px]">
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

      {/* ========== BACKLOG TAB ========== */}
      {tab === 'backlog' && (
        <>
          {blStats && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
              <StatsCard label="Total Items" value={blStats.total} />
              <StatsCard label="Bugs" value={blStats.bugs} />
              <StatsCard label="Features" value={blStats.features} />
              <StatsCard label="Open" value={blStats.reported + blStats.triaged + blStats.in_progress + (blStats.ready_for_test || 0)} />
            </div>
          )}

          {backlogLoading && <p className="text-slate-400">Loading...</p>}

          {!backlogLoading && (
            <div className="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-6 gap-4">
              {BACKLOG_COLUMNS.map((col) => {
                const items = allBacklog.filter((r) => r.status === col.key)
                const transitions = BACKLOG_TRANSITIONS[col.key] || []
                return (
                  <div key={col.key} className={`rounded-lg border-t-2 ${col.color} ${col.bg}`}>
                    <div className="p-4 border-b border-slate-700/50">
                      <div className="flex items-center justify-between">
                        <h3 className="font-semibold text-white text-sm">{col.label}</h3>
                        <span className="text-xs bg-slate-700 text-slate-300 px-2 py-0.5 rounded-full">
                          {items.length}
                        </span>
                      </div>
                    </div>
                    <div className="p-2 space-y-2 max-h-[calc(100vh-380px)] overflow-y-auto">
                      {items.length === 0 && (
                        <p className="text-slate-500 text-xs text-center py-6">Empty</p>
                      )}
                      {items.map((item: any) => (
                        <div key={item.id} className="bg-slate-800 rounded-lg p-3 space-y-2">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-1.5 mb-1">
                                <span
                                  className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                                    item.type === 'bug'
                                      ? 'bg-red-600/30 text-red-300'
                                      : 'bg-purple-600/30 text-purple-300'
                                  }`}
                                >
                                  {item.type}
                                </span>
                                <span
                                  className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${PRIORITY_STYLES[item.priority] || ''}`}
                                >
                                  {item.priority}
                                </span>
                              </div>
                              <p className="text-sm font-medium text-white leading-tight">{item.title}</p>
                              <p className="text-xs text-slate-400 mt-0.5">
                                {item.username} &middot; {new Date(item.created_at).toLocaleDateString()}
                              </p>
                            </div>
                            <button
                              onClick={() => backlogDeleteMutation.mutate(item.id)}
                              className="text-slate-500 hover:text-red-400 text-xs flex-shrink-0"
                              title="Delete"
                            >
                              x
                            </button>
                          </div>
                          {item.description && (
                            <p className="text-xs text-slate-400 line-clamp-2">{item.description}</p>
                          )}
                          {item.admin_note && (
                            <p className="text-xs text-slate-400 italic border-l-2 border-slate-600 pl-2">
                              {item.admin_note}
                            </p>
                          )}
                          {/* Priority selector */}
                          <div className="flex gap-1">
                            {['low', 'medium', 'high', 'critical'].map((p) => (
                              <button
                                key={p}
                                onClick={() => backlogMutation.mutate({ id: item.id, priority: p })}
                                className={`text-[10px] px-1.5 py-0.5 rounded transition-colors ${
                                  item.priority === p
                                    ? PRIORITY_STYLES[p]
                                    : 'bg-slate-700/50 text-slate-500 hover:text-slate-300'
                                }`}
                              >
                                {p}
                              </button>
                            ))}
                          </div>
                          {/* Status transitions */}
                          {transitions.length > 0 && (
                            <div className="flex flex-wrap gap-1.5 pt-1">
                              {transitions.map((t) => (
                                <button
                                  key={t.status}
                                  onClick={() => handleBacklogMove(item.id, t.status)}
                                  disabled={backlogMutation.isPending}
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

          {/* Mobile card view */}
          {!usersLoading && users && users.length > 0 && (
            <div className="md:hidden space-y-3">
              {users.map((u: any) => {
                const isSelf = u.user_id === currentUser?.id
                return (
                  <div key={u.user_id} className="bg-slate-800 rounded-lg p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-white">
                          {u.username}
                          {isSelf && <span className="ml-2 text-xs text-slate-500">(you)</span>}
                        </p>
                        <p className="text-xs text-slate-400 mt-0.5">
                          Joined {new Date(u.created_at).toLocaleDateString()}
                        </p>
                      </div>
                      <span
                        className={`text-xs px-2 py-1 rounded font-medium ${
                          u.role === 'admin'
                            ? 'bg-purple-600/30 text-purple-300'
                            : 'bg-slate-600/30 text-slate-300'
                        }`}
                      >
                        {u.role}
                      </span>
                    </div>
                    {!isSelf && (
                      <button
                        onClick={() => roleMutation.mutate({ userId: u.user_id, role: u.role === 'user' ? 'admin' : 'user' })}
                        disabled={roleMutation.isPending}
                        className={`w-full py-2 rounded text-xs font-medium transition-colors disabled:opacity-50 ${
                          u.role === 'user'
                            ? 'bg-purple-600 hover:bg-purple-700 text-white'
                            : 'bg-slate-600 hover:bg-slate-500 text-white'
                        }`}
                      >
                        {u.role === 'user' ? 'Promote to Admin' : 'Demote to User'}
                      </button>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {/* Desktop table view */}
          {!usersLoading && users && users.length > 0 && (
            <div className="hidden md:block bg-slate-800 rounded-lg overflow-hidden">
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

      {/* ========== HEALTH TAB ========== */}
      {tab === 'health' && (
        <div className="max-w-lg space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-slate-400 text-sm">Service connectivity status. Auto-refreshes every 30s.</p>
            <button
              onClick={() => refetchHealth()}
              className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
            >
              Refresh
            </button>
          </div>

          {healthLoading && <p className="text-slate-400">Checking services...</p>}

          {!healthLoading && healthData && (
            <div className="space-y-3">
              {/* Jellyfin */}
              <div className="bg-slate-800 rounded-lg p-5">
                <div className="flex items-center gap-3 mb-2">
                  <div className={`w-3 h-3 rounded-full flex-shrink-0 ${
                    healthData.jellyfin?.status === 'ok' ? 'bg-green-500' : 'bg-red-500'
                  }`} />
                  <h3 className="text-white font-medium">Jellyfin</h3>
                </div>
                {healthData.jellyfin?.status === 'ok' ? (
                  <div className="ml-6 space-y-2">
                    <div className="space-y-1">
                      <p className="text-sm text-slate-300">{healthData.jellyfin.server_name}</p>
                      <p className="text-xs text-slate-400">Version {healthData.jellyfin.version}</p>
                      <p className="text-xs text-slate-500">{healthData.jellyfin.url}</p>
                    </div>
                    <button
                      onClick={() => scanMutation.mutate()}
                      disabled={scanMutation.isPending}
                      className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 text-white px-4 py-1.5 rounded text-xs font-medium transition-colors"
                    >
                      {scanMutation.isPending ? 'Scanning...' : 'Scan Library'}
                    </button>
                    {scanMutation.isSuccess && (
                      <p className="text-green-400 text-xs">Library scan started.</p>
                    )}
                    {scanMutation.isError && (
                      <p className="text-red-400 text-xs">
                        {(scanMutation.error as any)?.response?.data?.detail || 'Failed to start scan'}
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="ml-6">
                    <p className="text-sm text-red-400">Unreachable</p>
                    <p className="text-xs text-slate-500">{healthData.jellyfin?.url}</p>
                    {healthData.jellyfin?.detail && (
                      <p className="text-xs text-slate-500 mt-1">{healthData.jellyfin.detail}</p>
                    )}
                  </div>
                )}
              </div>

              {/* TMDB */}
              <div className="bg-slate-800 rounded-lg p-5">
                <div className="flex items-center gap-3 mb-2">
                  <div className={`w-3 h-3 rounded-full flex-shrink-0 ${
                    healthData.tmdb?.status === 'ok' ? 'bg-green-500' : 'bg-red-500'
                  }`} />
                  <h3 className="text-white font-medium">TMDB API</h3>
                </div>
                <div className="ml-6">
                  <p className="text-sm text-slate-300">
                    {healthData.tmdb?.status === 'ok' ? 'Connected' : 'Unreachable'}
                  </p>
                  {healthData.tmdb?.detail && (
                    <p className="text-xs text-slate-500 mt-1">{healthData.tmdb.detail}</p>
                  )}
                </div>
              </div>

              {/* Database */}
              <div className="bg-slate-800 rounded-lg p-5">
                <div className="flex items-center gap-3 mb-2">
                  <div className={`w-3 h-3 rounded-full flex-shrink-0 ${
                    healthData.database?.status === 'ok' ? 'bg-green-500' : 'bg-red-500'
                  }`} />
                  <h3 className="text-white font-medium">Database</h3>
                </div>
                <div className="ml-6">
                  <p className="text-sm text-slate-300">
                    {healthData.database?.status === 'ok' ? 'Connected' : 'Error'}
                  </p>
                  {healthData.database?.detail && (
                    <p className="text-xs text-slate-500 mt-1">{healthData.database.detail}</p>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ========== TUNNEL TAB ========== */}
      {tab === 'tunnel' && (
        <div className="max-w-lg">
          <p className="text-slate-400 text-sm mb-6">
            Expose the app to the internet via an ngrok tunnel. Requires an ngrok authtoken configured in the backend <code className="text-slate-300">.env</code> file.
          </p>

          {tunnelLoading && <p className="text-slate-400">Checking tunnel status...</p>}

          {!tunnelLoading && tunnelData && (
            <div className="bg-slate-800 rounded-lg p-6 space-y-4">
              <div className="flex items-center gap-3">
                <div
                  className={`w-3 h-3 rounded-full ${
                    tunnelData.active ? 'bg-green-500 animate-pulse' : 'bg-slate-600'
                  }`}
                />
                <span className="text-white font-medium">
                  {tunnelData.active ? 'Tunnel Active' : 'Tunnel Inactive'}
                </span>
              </div>

              {tunnelData.active && tunnelData.url && (
                <div className="bg-slate-700 rounded-lg p-4">
                  <p className="text-xs text-slate-400 mb-1">Public URL</p>
                  <a
                    href={tunnelData.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-400 hover:text-blue-300 text-sm break-all"
                  >
                    {tunnelData.url}
                  </a>
                  <button
                    onClick={() => navigator.clipboard.writeText(tunnelData.url!)}
                    className="ml-3 text-xs text-slate-400 hover:text-white transition-colors"
                  >
                    Copy
                  </button>
                </div>
              )}

              <div className="flex gap-3">
                {!tunnelData.active ? (
                  <button
                    onClick={() => startTunnelMutation.mutate()}
                    disabled={startTunnelMutation.isPending}
                    className="bg-green-600 hover:bg-green-700 disabled:bg-green-800 text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors"
                  >
                    {startTunnelMutation.isPending ? 'Starting...' : 'Start Tunnel'}
                  </button>
                ) : (
                  <button
                    onClick={() => stopTunnelMutation.mutate()}
                    disabled={stopTunnelMutation.isPending}
                    className="bg-red-600 hover:bg-red-700 disabled:bg-red-800 text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors"
                  >
                    {stopTunnelMutation.isPending ? 'Stopping...' : 'Stop Tunnel'}
                  </button>
                )}
              </div>

              {startTunnelMutation.isError && (
                <p className="text-red-400 text-sm">
                  {(startTunnelMutation.error as any)?.response?.data?.detail || 'Failed to start tunnel'}
                </p>
              )}
              {stopTunnelMutation.isError && (
                <p className="text-red-400 text-sm">
                  {(stopTunnelMutation.error as any)?.response?.data?.detail || 'Failed to stop tunnel'}
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Backlog Note Modal */}
      {blNoteModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-xl p-6 w-full max-w-md shadow-xl">
            <h3 className="text-lg font-semibold text-white mb-1">Update Backlog Item</h3>
            <p className="text-sm text-slate-400 mb-4">
              Moving to <span className="font-medium text-white capitalize">{blNoteModal.status.replace('_', ' ')}</span>. Add an optional note:
            </p>
            <textarea
              value={blNoteText}
              onChange={(e) => setBlNoteText(e.target.value)}
              placeholder="Optional note..."
              rows={3}
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            />
            <div className="flex justify-end gap-3 mt-4">
              <button
                onClick={() => setBlNoteModal(null)}
                className="px-4 py-2 text-sm text-slate-300 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmBacklogMove}
                disabled={backlogMutation.isPending}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 text-white text-sm rounded-lg font-medium transition-colors"
              >
                {backlogMutation.isPending ? 'Updating...' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Note Modal */}
      {noteModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
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
