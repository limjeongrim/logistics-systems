import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import useAuthStore from '../store/authStore'

const ROLE_HOME = {
  ADMIN: '/admin',
  WORKER: '/worker',
  SELLER: '/seller',
}

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const login = useAuthStore((s) => s.login)
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const user = await login(email, password)
      navigate(ROLE_HOME[user.role] ?? '/')
    } catch (err) {
      setError(err.response?.data?.detail ?? '로그인에 실패했습니다. 다시 시도해주세요.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="w-full max-w-md">

        {/* Branding */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-extrabold text-indigo-600 tracking-tight">FullFit</h1>
          <p className="mt-2 text-gray-500 text-sm">뷰티 이커머스 풀필먼트 플랫폼</p>
        </div>

        {/* Login card */}
        <div className="bg-white shadow-lg rounded-2xl p-8">
          <h2 className="text-xl font-semibold text-gray-800 mb-6">로그인</h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">이메일</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="example@fullfit.com"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">비밀번호</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="비밀번호를 입력하세요"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-3 py-2">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white font-semibold py-2.5 rounded-lg text-sm transition-colors"
            >
              {loading ? '로그인 중...' : '로그인'}
            </button>
          </form>
        </div>

        {/* Dev hint */}
        <p className="text-center text-xs text-gray-400 mt-4">
          테스트 계정: admin / worker / seller @fullfit.com
        </p>
      </div>
    </div>
  )
}
