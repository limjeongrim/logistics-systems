import { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import useAuthStore from './store/authStore'
import ProtectedRoute from './routes/ProtectedRoute'
import LoginPage from './pages/LoginPage'
import AdminDashboard from './pages/admin/AdminDashboard'
import WorkerDashboard from './pages/worker/WorkerDashboard'
import SellerDashboard from './pages/seller/SellerDashboard'

const ROLE_HOME = {
  ADMIN: '/admin',
  WORKER: '/worker',
  SELLER: '/seller',
}

/** Redirect authenticated users to their role dashboard; others to /login. */
function RootRedirect() {
  const { isAuthenticated, user } = useAuthStore()
  if (!isAuthenticated || !user) return <Navigate to="/login" replace />
  return <Navigate to={ROLE_HOME[user.role] ?? '/login'} replace />
}

export default function App() {
  const loadFromStorage = useAuthStore((s) => s.loadFromStorage)

  // Rehydrate auth state from localStorage refresh token on every page load
  useEffect(() => {
    loadFromStorage()
  }, [loadFromStorage])

  return (
    <BrowserRouter>
      <Routes>
        {/* Public */}
        <Route path="/login" element={<LoginPage />} />

        {/* Root: redirect based on role */}
        <Route path="/" element={<RootRedirect />} />

        {/* Role-protected dashboards */}
        <Route
          path="/admin/*"
          element={
            <ProtectedRoute allowedRole="ADMIN">
              <AdminDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/worker/*"
          element={
            <ProtectedRoute allowedRole="WORKER">
              <WorkerDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/seller/*"
          element={
            <ProtectedRoute allowedRole="SELLER">
              <SellerDashboard />
            </ProtectedRoute>
          }
        />

        {/* Catch-all */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
