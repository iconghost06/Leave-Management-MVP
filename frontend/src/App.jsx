import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { homePathFor, RequireAuth, RequireManager, useAuth } from "./auth/AuthContext.jsx";
import NavBar from "./components/NavBar.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import ManagerQueuePage from "./pages/ManagerQueuePage.jsx";
import MyRequestsPage from "./pages/MyRequestsPage.jsx";
import NewRequestPage from "./pages/NewRequestPage.jsx";
import RequestDetailPage from "./pages/RequestDetailPage.jsx";
import SignupPage from "./pages/SignupPage.jsx";

function Layout() {
  return (
    <>
      <NavBar />
      <main className="content">
        <Outlet />
      </main>
    </>
  );
}

// "/" sends each role to its home page.
function HomeRedirect() {
  const { role } = useAuth();
  return <Navigate to={homePathFor(role)} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<Layout />}>
          <Route path="/" element={<HomeRedirect />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/requests/new" element={<NewRequestPage />} />
          <Route path="/requests" element={<MyRequestsPage />} />
          <Route path="/requests/:id" element={<RequestDetailPage />} />
          <Route element={<RequireManager />}>
            <Route path="/manager/queue" element={<ManagerQueuePage />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
