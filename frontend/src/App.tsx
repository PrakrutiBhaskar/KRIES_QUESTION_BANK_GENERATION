import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppProvider } from './hooks/useApp';
import AppLayout from './layouts/AppLayout';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import GeneratePage from './pages/GeneratePage';
import QuestionBanksPage from './pages/QuestionBanksPage';
import QuestionBankDetailPage from './pages/QuestionBankDetailPage';
import SettingsPage from './pages/SettingsPage';

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Routes>
          {/* Public */}
          <Route path="/login" element={<LoginPage />} />

          {/* Protected — wrapped in AppLayout */}
          <Route element={<AppLayout />}>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/generate" element={<GeneratePage />} />
            <Route path="/question-banks" element={<QuestionBanksPage />} />
            <Route path="/question-banks/:id" element={<QuestionBankDetailPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>

          {/* Default redirect */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </AppProvider>
  );
}
