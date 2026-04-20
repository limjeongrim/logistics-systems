import { useNavigate } from 'react-router-dom'
import useAuthStore from '../../store/authStore'

// Seller accent: violet/purple — brand-friendly, cosmetics feel
export default function SellerDashboard() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const modules = [
    { label: '내 주문 현황', desc: '주문 접수·처리·배송 현황 조회', icon: '🛒' },
    { label: '재고 조회',   desc: '상품별 보유 재고 및 입출고 내역', icon: '📋' },
    { label: '정산 내역',   desc: '월별 정산 금액 및 수수료 확인',  icon: '💳' },
    { label: '상품 관리',   desc: '판매 상품 등록 및 정보 수정',    icon: '🧴' },
  ]

  return (
    <div className="min-h-screen bg-violet-50">
      {/* Nav */}
      <nav className="bg-violet-600 px-6 py-4 flex items-center justify-between shadow">
        <div className="flex items-center gap-3">
          <span className="text-xl font-extrabold text-white">FullFit</span>
          <span className="bg-violet-400 text-white text-xs font-bold px-2 py-0.5 rounded-full border border-violet-300">
            SELLER
          </span>
        </div>
        <button
          onClick={handleLogout}
          className="text-violet-100 hover:text-white text-sm transition-colors"
        >
          로그아웃
        </button>
      </nav>

      {/* Content */}
      <main className="p-8">
        <div className="max-w-3xl mx-auto">
          <h1 className="text-2xl font-bold text-violet-900 mb-1">
            안녕하세요, {user?.full_name}님
          </h1>
          <p className="text-violet-500 text-sm mb-8">역할: 셀러 (SELLER)</p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {modules.map((m) => (
              <div
                key={m.label}
                className="bg-white border border-violet-200 rounded-xl p-5 hover:border-violet-500 hover:shadow-md transition-all cursor-pointer"
              >
                <div className="text-2xl mb-3">{m.icon}</div>
                <h3 className="text-violet-900 font-semibold text-sm">{m.label}</h3>
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
