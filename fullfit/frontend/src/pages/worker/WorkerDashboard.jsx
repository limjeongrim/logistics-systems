import { useNavigate } from 'react-router-dom'
import useAuthStore from '../../store/authStore'

// Worker accent: emerald green — active, operational feel
export default function WorkerDashboard() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const modules = [
    { label: '피킹 작업', desc: '오늘의 피킹 주문 목록 및 경로 안내', icon: '🗂️' },
    { label: '패킹 작업', desc: '피킹 완료 주문 포장 처리',           icon: '📫' },
    { label: '입고 처리', desc: '입고 상품 바코드 스캔 및 등록',       icon: '📥' },
    { label: '출고 처리', desc: '출고 확인 및 송장 출력',             icon: '📤' },
  ]

  return (
    <div className="min-h-screen bg-emerald-50">
      {/* Nav */}
      <nav className="bg-emerald-700 px-6 py-4 flex items-center justify-between shadow">
        <div className="flex items-center gap-3">
          <span className="text-xl font-extrabold text-white">FullFit</span>
          <span className="bg-emerald-500 text-white text-xs font-bold px-2 py-0.5 rounded-full border border-emerald-300">
            WORKER
          </span>
        </div>
        <button
          onClick={handleLogout}
          className="text-emerald-100 hover:text-white text-sm transition-colors"
        >
          로그아웃
        </button>
      </nav>

      {/* Content */}
      <main className="p-8">
        <div className="max-w-3xl mx-auto">
          <h1 className="text-2xl font-bold text-emerald-900 mb-1">
            안녕하세요, {user?.full_name}님
          </h1>
          <p className="text-emerald-600 text-sm mb-8">역할: 창고 작업자 (WORKER)</p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {modules.map((m) => (
              <div
                key={m.label}
                className="bg-white border border-emerald-200 rounded-xl p-5 hover:border-emerald-500 hover:shadow-md transition-all cursor-pointer"
              >
                <div className="text-2xl mb-3">{m.icon}</div>
                <h3 className="text-emerald-900 font-semibold text-sm">{m.label}</h3>
                <p className="text-gray-500 text-xs mt-1">{m.desc}</p>
                <span className="text-xs text-gray-400 mt-3 block">Phase 2에서 구현 예정</span>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}
