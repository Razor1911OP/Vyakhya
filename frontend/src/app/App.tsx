import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { AuthProvider, useAuth } from '../shared/auth/AuthProvider'
import { RequireAuth, RequirePanel } from '../shared/auth/RequireRole'
import { homePathFor } from '../shared/auth/permissions'
import { AnalysisPanel } from '../panels/analysis/AnalysisPanel'
import { DetectionPanel } from '../panels/detection/DetectionPanel'
import { EvaluationPanel } from '../panels/evaluation/EvaluationPanel'
import { SimulatorPanel } from '../panels/simulator/SimulatorPanel'
import { AppLayout } from './AppLayout'
import { LoginPage } from './LoginPage'

function Home() {
  const { user } = useAuth()
  return <Navigate to={user ? homePathFor(user.role) : '/login'} replace />
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<Home />} />
        <Route path="simulator" element={<RequirePanel panel="simulator"><SimulatorPanel /></RequirePanel>} />
        <Route path="detection" element={<RequirePanel panel="detection"><DetectionPanel /></RequirePanel>} />
        <Route path="analysis" element={<RequirePanel panel="analysis"><AnalysisPanel /></RequirePanel>} />
        <Route path="evaluation" element={<RequirePanel panel="evaluation"><EvaluationPanel /></RequirePanel>} />
      </Route>
      <Route path="*" element={<Home />} />
    </Routes>
  )
}

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  )
}
