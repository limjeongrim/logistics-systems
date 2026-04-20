import { Navigate } from 'react-router-dom'
import useAuthStore from '../store/authStore'

// Maps each role to its default landing path
const ROLE_HOME = {
  ADMIN: '/admin',
  WORKER: '/worker',
  SELLER: '/seller',
}

/**
 * Wraps a route with authentication + role enforcement.
 *
 *  - Not authenticated        → redirect to /login
 *  - Wrong role for this route → redirect to the user's own dashboard
 *  - Correct role             → render children
 */
export default function ProtectedRoute({ children, allowedRole }) {
  const { isAuthenticated, user } = useAuthStore()

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" replace />
  }

  if (allowedRole && user.role !== allowedRole) {
    return <Navigate to={ROLE_HOME[user.role] ?? '/login'} replace />
  }

  return children
}
