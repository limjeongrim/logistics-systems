import { create } from 'zustand'
import axiosInstance from '../api/axiosInstance'

/**
 * Auth store (Zustand)
 *
 * Token strategy:
 *   - Access token  → in-memory only (window.__fullfit_access_token)
 *                     Never written to localStorage to reduce XSS exposure.
 *   - Refresh token → localStorage so sessions survive page refresh.
 */
const useAuthStore = create((set) => ({
  // ── State ────────────────────────────────────────────────────────────────
  user: null,            // { id, email, role, full_name }
  isAuthenticated: false,

  // ── Actions ──────────────────────────────────────────────────────────────

  /**
   * POST /auth/login → store tokens → GET /auth/me → update state.
   * Returns the user object so the caller can redirect by role.
   */
  login: async (email, password) => {
    const loginRes = await axiosInstance.post('/auth/login', { email, password })
    const { access_token, refresh_token } = loginRes.data

    // Store tokens
    window.__fullfit_access_token = access_token
    localStorage.setItem('fullfit_refresh_token', refresh_token)

    // Fetch full user profile (uses the access token via the request interceptor)
    const meRes = await axiosInstance.get('/auth/me')
    set({ user: meRes.data, isAuthenticated: true })

    return meRes.data
  },

  logout: () => {
    window.__fullfit_access_token = null
    localStorage.removeItem('fullfit_refresh_token')
    set({ user: null, isAuthenticated: false })
  },

  /**
   * Called on app mount to rehydrate state from a stored refresh token.
   * Silently resolves to nothing if the token is missing or expired.
   */
  loadFromStorage: async () => {
    const refreshToken = localStorage.getItem('fullfit_refresh_token')
    if (!refreshToken) return

    try {
      const res = await axiosInstance.post('/auth/refresh', {
        refresh_token: refreshToken,
      })
      window.__fullfit_access_token = res.data.access_token

      const meRes = await axiosInstance.get('/auth/me')
      set({ user: meRes.data, isAuthenticated: true })
    } catch {
      // Refresh token expired or server unreachable — start fresh
      localStorage.removeItem('fullfit_refresh_token')
      set({ user: null, isAuthenticated: false })
    }
  },
}))

export default useAuthStore
