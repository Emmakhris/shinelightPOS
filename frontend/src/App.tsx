import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { api, setUnauthorizedHandler } from './api/client'
import { ApprovalDialog } from './components/approval'
import { PrintHost } from './components/print'
import { Toaster } from './components/toast'
import { Loading } from './components/ui'
import { AppLayout } from './layout/AppLayout'
import { useSettings } from './lib/hooks'
import { DashboardPage } from './pages/DashboardPage'
import { LockScreen, LoginPage } from './pages/LoginPage'
import { SetupPage } from './pages/SetupPage'
import { CustomersPage } from './pages/customers/CustomersPage'
import { InventoryPage } from './pages/inventory/InventoryPage'
import { RegisterPage } from './pages/pos/RegisterPage'
import { ProductsPage } from './pages/products/ProductsPage'
import { ReportsPage } from './pages/reports/ReportsPage'
import { FloorPage } from './pages/restaurant/FloorPage'
import { OrderPage } from './pages/restaurant/OrderPage'
import { SalesPage } from './pages/sales/SalesPage'
import { SettingsPage } from './pages/settings/SettingsPage'
import { ShiftsPage } from './pages/shifts/ShiftsPage'
import { UsersPage } from './pages/users/UsersPage'
import { useAuth } from './stores/auth'

export default function App() {
  const { user, loading, locked, init, logout } = useAuth()
  const qc = useQueryClient()
  const setup = useQuery({
    queryKey: ['setup-status'],
    queryFn: () => api.get<{ setup_complete: boolean; business_name: string }>('/setup/status/'),
  })

  useEffect(() => {
    init()
    setUnauthorizedHandler(() => logout())
  }, [init, logout])

  // A different person signed in: drop everything cached for the previous one.
  useEffect(() => {
    qc.removeQueries({ predicate: (q) => q.queryKey[0] !== 'setup-status' })
  }, [user?.id, qc])

  let content
  if (setup.isLoading || loading) content = <Loading />
  else if (setup.data && !setup.data.setup_complete) content = <SetupPage />
  else if (locked) content = <LockScreen />
  else if (!user) content = <LoginPage businessName={setup.data?.business_name} />
  else content = <Authed />

  return (
    <>
      {content}
      <Toaster />
      <ApprovalDialog />
      <PrintHost />
    </>
  )
}

function Authed() {
  const settings = useSettings()
  const can = useAuth((s) => s.can)
  if (settings.isLoading) return <Loading />
  const s = settings.data
  const home = can('view_reports') ? '/' : s?.retail_mode ? '/pos' : '/tables'
  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={can('view_reports') ? <DashboardPage /> : <Navigate to={home} replace />} />
        <Route path="/pos" element={<RegisterPage />} />
        <Route path="/tables" element={<FloorPage />} />
        <Route path="/tables/order/:id" element={<OrderPage />} />
        <Route path="/sales" element={<SalesPage />} />
        <Route path="/products" element={<ProductsPage />} />
        <Route path="/inventory" element={<InventoryPage />} />
        <Route path="/customers" element={<CustomersPage />} />
        <Route path="/shifts" element={<ShiftsPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/users" element={<UsersPage />} />
        <Route path="*" element={<Navigate to={home} replace />} />
      </Routes>
    </AppLayout>
  )
}
