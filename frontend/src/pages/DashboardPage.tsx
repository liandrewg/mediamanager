import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../context/AuthContext'
import { getLibraryStats, getRecentlyAdded } from '../api/jellyfin'
import { getMyRequests, getAdminStats } from '../api/requests'
import StatsCard from '../components/StatsCard'
import RequestBadge from '../components/RequestBadge'
import { Link } from 'react-router-dom'

export default function DashboardPage() {
  const { user } = useAuth()

  const { data: libraryStats } = useQuery({
    queryKey: ['libraryStats'],
    queryFn: getLibraryStats,
  })

  const { data: recentItems } = useQuery({
    queryKey: ['recentlyAdded'],
    queryFn: () => getRecentlyAdded(12),
  })

  const { data: myRequests } = useQuery({
    queryKey: ['myRequests', 'dashboard'],
    queryFn: () => getMyRequests(1, 5),
  })

  const { data: adminStats } = useQuery({
    queryKey: ['adminStats'],
    queryFn: getAdminStats,
    enabled: user?.is_admin ?? false,
  })

  return (
    <div>
      <h2 className="text-2xl font-bold text-white mb-2">Welcome, {user?.username}</h2>
      <p className="text-slate-400 mb-8">Here's an overview of your media library and requests.</p>

      {/* Library Stats */}
      {libraryStats && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-8">
          <StatsCard label="Movies" value={libraryStats.total_movies} />
          <StatsCard label="TV Shows" value={libraryStats.total_shows} />
          <StatsCard label="Episodes" value={libraryStats.total_episodes} />
        </div>
      )}

      {/* Admin Stats */}
      {user?.is_admin && adminStats && (
        <div className="mb-8">
          <h3 className="text-lg font-semibold text-white mb-3">Request Overview</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatsCard label="Pending Requests" value={adminStats.pending} />
            <StatsCard label="Approved" value={adminStats.approved} />
            <StatsCard label="Fulfilled" value={adminStats.fulfilled} />
            <StatsCard label="Total Requests" value={adminStats.total} />
          </div>
        </div>
      )}

      {/* Recent Requests */}
      {myRequests?.items && myRequests.items.length > 0 && (
        <div className="mb-8">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-lg font-semibold text-white">Your Recent Requests</h3>
            <Link to="/my-requests" className="text-sm text-blue-400 hover:text-blue-300">
              View all
            </Link>
          </div>
          <div className="bg-slate-800 rounded-lg divide-y divide-slate-700">
            {myRequests.items.map((req: any) => (
              <div key={req.id} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <span className="text-white text-sm truncate block">{req.title}</span>
                  <span className="text-slate-500 text-xs uppercase">{req.media_type}</span>
                </div>
                <div className="flex-shrink-0">
                  <RequestBadge status={req.status} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recently Added */}
      {recentItems && recentItems.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold text-white mb-3">Recently Added to Library</h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
            {recentItems.map((item: any) => (
              <div key={item.jellyfin_id} className="bg-slate-800 rounded-lg overflow-hidden">
                <div className="aspect-[2/3] bg-slate-700">
                  {item.poster_url ? (
                    <img src={item.poster_url} alt={item.title} className="w-full h-full object-cover" loading="lazy" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-slate-500 text-sm">No Poster</div>
                  )}
                </div>
                <div className="p-2">
                  <p className="text-xs text-white truncate">{item.title}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
