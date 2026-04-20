import axios from 'axios'

const axiosInstance = axios.create({
  baseURL: 'http://localhost:8000',
})

// ─── Request Interceptor ────────────────────────────────────────────────────
// Attach the access token (kept in memory via window.__fullfit_access_token)
// to every outgoing request. This avoids XSS risks of localStorage for the
// short-lived access token while still providing automatic auth headers.
axiosInstance.interceptors.request.use(
  (config) => {
    const token = window.__fullfit_access_token
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

// ─── Response Interceptor ───────────────────────────────────────────────────
// On 401: attempt a silent token refresh using the stored refresh token,
// then replay the original request once. On second failure, force logout.
axiosInstance.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    // Only attempt refresh once (guard with _retry flag)
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      try {
        const refreshToken = localStorage.getItem('fullfit_refresh_token')
        if (!refreshToken) throw new Error('No refresh token available')

        // Use plain axios (not the instance) to avoid triggering this interceptor again
        const res = await axios.post('http://localhost:8000/auth/refresh', {
          refresh_token: refreshToken,
        })

        const newAccessToken = res.data.access_token
        window.__fullfit_access_token = newAccessToken
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`

        return axiosInstance(originalRequest)
      } catch {
        // Refresh failed — clear all auth state and redirect to login
        localStorage.removeItem('fullfit_refresh_token')
        window.__fullfit_access_token = null
        window.location.href = '/login'
      }
    }

    return Promise.reject(error)
  },
)

export default axiosInstance
