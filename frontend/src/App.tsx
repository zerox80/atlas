import {
  BrowserRouter as Router,
  Routes,
  Route,
  Navigate,
  useNavigate,
} from "react-router-dom";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Contracts from "./pages/Contracts";
import Invoices from "./pages/Invoices";
import AdminPanel from "./pages/AdminPanel";
import Lists from "./pages/Lists";
import Calendar from "./pages/Calendar";
import ProtectedContracts from "./pages/ProtectedContracts";
import Layout from "./components/Layout";
import { useState, useEffect, createContext, useContext } from "react";
import api from "./api";

// User Context
interface UserInfo {
  id: number;
  username: string;
  role: string;
  has_2fa: boolean;
}

const isUserInfo = (value: unknown): value is UserInfo => {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<UserInfo>;
  return (
    typeof candidate.id === "number" &&
    typeof candidate.username === "string" &&
    typeof candidate.role === "string"
  );
};

interface UserContextType {
  user: UserInfo | null;
  setUser: (user: UserInfo | null) => void;
  isAdmin: boolean;
}

export const UserContext = createContext<UserContextType>({
  user: null,
  setUser: () => {},
  isAdmin: false,
});

export const useUser = () => useContext(UserContext);

export function AppRoutes() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [user, setUser] = useState<UserInfo | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const checkAuth = async () => {
      try {
        // First check if authenticated by calling /me
        const meRes = await api.get<UserInfo>("/me");
        if (!isUserInfo(meRes.data)) throw new Error("Invalid user response");
        setUser(meRes.data);
        setIsAuthenticated(true);
      } catch {
        setIsAuthenticated(false);
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    };
    void checkAuth();
  }, []);

  const handleLoginSuccess = async () => {
    try {
      const meRes = await api.get<UserInfo>("/me");
      if (!isUserInfo(meRes.data)) throw new Error("Invalid user response");
      setUser(meRes.data);
      setIsAuthenticated(true);
      navigate("/");
    } catch {
      console.error("Failed to get user info after login");
    }
  };

  if (isLoading) {
    return (
      <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#070907] text-white">
        <div className="ambient-grid absolute inset-0 opacity-40" />
        <div className="relative flex flex-col items-center">
          <div
            className={[
              "flex h-14 w-14 items-center justify-center rounded-[20px] bg-[#b8f15a]",
              "text-lg font-black tracking-[-0.08em] text-[#111700]",
              "shadow-[0_0_50px_rgba(184,241,90,.18)]",
            ].join(" ")}
          >
            AT
          </div>
          <div className="mt-5 h-1 w-24 overflow-hidden rounded-full bg-white/[0.07]">
            <div className="h-full w-1/2 animate-pulse rounded-full bg-[#b8f15a]" />
          </div>
          <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em] text-white/30">
            Atlas lädt
          </p>
        </div>
      </div>
    );
  }

  return (
    <UserContext.Provider
      value={{ user, setUser, isAdmin: user?.role === "admin" }}
    >
      <Routes>
        <Route
          path="/login"
          element={
            isAuthenticated ? (
              <Navigate to="/" />
            ) : (
              <Login onLoginSuccess={handleLoginSuccess} />
            )
          }
        />
        <Route
          path="/"
          element={
            isAuthenticated ? (
              <Layout>
                <Dashboard />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        <Route
          path="/contracts"
          element={
            isAuthenticated ? (
              <Layout>
                <Contracts />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        <Route
          path="/invoices"
          element={
            isAuthenticated ? (
              <Layout>
                <Invoices />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        <Route
          path="/lists"
          element={
            isAuthenticated ? (
              <Layout>
                <Lists />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        <Route
          path="/calendar"
          element={
            isAuthenticated ? (
              <Layout>
                <Calendar />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        <Route
          path="/protected"
          element={
            isAuthenticated ? (
              <Layout>
                <ProtectedContracts />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        <Route
          path="/admin"
          element={
            isAuthenticated && user?.role === "admin" ? (
              <Layout>
                <AdminPanel />
              </Layout>
            ) : (
              <Navigate to="/" />
            )
          }
        />
      </Routes>
    </UserContext.Provider>
  );
}

function App() {
  return (
    <Router>
      <AppRoutes />
    </Router>
  );
}

export default App;
