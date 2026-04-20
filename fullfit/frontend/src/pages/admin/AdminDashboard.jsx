import { useNavigate } from 'react-router-dom'
import useAuthStore from '../../store/authStore'

// Admin accent: dark slate / red — communicates authority and full system access
export default function AdminDashboard() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const modules = [
    { label: '주문 관리',      desc: '전체 주문 현황 및 처리 내역', icon: '📦' },
    { label: '재고 관리',      desc: '입출고 현황 및 재고 조정',    icon: '🏭' },
    { label: '정산 관리',      desc: '셀러별 정산 내역 및 수수료',  icon: '💰' },
    { label: '작업자 관리',    desc: '피킹·패킹 작업 배정 및 현황', icon: '👷' },
    { label: '셀러 관리',      desc: '셀러 계정 및 상품 관리',     icon: '🛍️' },
    { label: '통계 대시보드',  desc: '물류 KPI 및 처리량 분석',    icon: '📊' },
  ]

  return (
    <div className="min-h-screen bg-slate-900">
      {/* Nav */}
      <nav className="bg-slate-800 border-b border-slate-700 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xl font-extrabold text-white">FullFit</span>
          <span className="bg-red-500 text-white text-xs font-bold px-2 py-0.5 rounded-full">
            ADMIN
          </span>
        </div>
        <button
          onClick={handleLogout}
          className="text-slate-400 hover:text-white text-sm transition-colors"
        >
          로그아웃
        </button>
      </nav>

      {/* Content */}
      <main className="p-8">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-2xl font-bold text-white mb-1">
            안녕하세요, {user?.full_name}님
          </h1>
          <p className="text-slate-400 text-sm mb-8">역할: 운영 관리자 (ADMIN)</p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {modules.map((m) => (
              <div
                key={m.label}
                className="bg-slate-800 border border-slate-700 rounded-xl p-5 hover:border-red-500 transition-colors cursor-pointer"
              >
                <div className="text-2xl mb-3">{m.icon}</div>
                <h3 className="text-white font-semibold text-sm">{m.label}</h3>
                <p className="text-slate-400 text-xs mt-1">{m.desc}</p>
                <span className="text-xs text-slate-600 mt-3 block">Phase 2에서 구현 예정</span>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}
