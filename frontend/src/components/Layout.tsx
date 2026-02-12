import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const navItems = [
  { to: '/', label: 'Dashboard' },
  { to: '/search', label: 'Search' },
  { to: '/library', label: 'Library' },
  { to: '/my-requests', label: 'My Requests' },
  { to: '/report', label: 'Report Issue' },
]

export default function Layout() {
  const { user, logout } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()

  const closeMenu = () => setMenuOpen(false)

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `block px-4 py-2.5 rounded-lg text-sm transition-colors ${
      isActive
        ? 'bg-blue-600 text-white'
        : 'text-slate-300 hover:bg-slate-800 hover:text-white'
    }`

  const navContent = (
    <>
      <div className="p-6">
        <h1 className="text-xl font-bold text-blue-400">Media Manager</h1>
      </div>
      <nav className="flex-1 px-4 space-y-1">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={linkClass}
            onClick={closeMenu}
          >
            {item.label}
          </NavLink>
        ))}
        {user?.is_admin && (
          <NavLink to="/admin" className={linkClass} onClick={closeMenu}>
            Admin
          </NavLink>
        )}
      </nav>
      <div className="p-4 border-t border-slate-700">
        <p className="text-sm text-slate-400 mb-2">{user?.username}</p>
        <button
          onClick={() => { logout(); closeMenu() }}
          className="text-sm text-slate-400 hover:text-white transition-colors"
        >
          Logout
        </button>
      </div>
    </>
  )

  return (
    <div className="min-h-screen flex flex-col md:flex-row">
      {/* Mobile header */}
      <header className="md:hidden bg-slate-900 border-b border-slate-700 flex items-center justify-between px-4 py-3 sticky top-0 z-40">
        <h1 className="text-lg font-bold text-blue-400">Media Manager</h1>
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          className="text-slate-300 hover:text-white p-1"
          aria-label="Toggle menu"
        >
          {menuOpen ? (
            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          )}
        </button>
      </header>

      {/* Mobile overlay */}
      {menuOpen && (
        <div className="md:hidden fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/60" onClick={closeMenu} />
          <aside className="absolute top-0 left-0 bottom-0 w-64 bg-slate-900 flex flex-col z-50 overflow-y-auto">
            {navContent}
          </aside>
        </div>
      )}

      {/* Desktop sidebar */}
      <aside className="hidden md:flex w-64 bg-slate-900 border-r border-slate-700 flex-col flex-shrink-0 sticky top-0 h-screen">
        {navContent}
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="max-w-7xl mx-auto p-4 md:p-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
