import { Route, Routes } from "react-router";
import RequireAuth from "./auth/RequireAuth.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import HostedChatPage from "./pages/HostedChatPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import NotFoundPage from "./pages/NotFoundPage.jsx";
import RegisterPage from "./pages/RegisterPage.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <DashboardPage />
          </RequireAuth>
        }
      />
      <Route path="/c/:publicId" element={<HostedChatPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
