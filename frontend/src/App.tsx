import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import AdminRoute from './components/AdminRoute'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import SearchPage from './pages/SearchPage'
import MediaDetailPage from './pages/MediaDetailPage'
import LibraryPage from './pages/LibraryPage'
import MyRequestsPage from './pages/MyRequestsPage'
import AdminPage from './pages/AdminPage'
import ReportPage from './pages/ReportPage'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/movie/:tmdbId" element={<MediaDetailPage mediaType="movie" />} />
          <Route path="/tv/:tmdbId" element={<MediaDetailPage mediaType="tv" />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/my-requests" element={<MyRequestsPage />} />
          <Route path="/report" element={<ReportPage />} />
          <Route element={<AdminRoute />}>
            <Route path="/admin" element={<AdminPage />} />
          </Route>
        </Route>
      </Route>
    </Routes>
  )
}

export default App
