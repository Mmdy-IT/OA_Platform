import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { Spin } from "antd";
import { api, ApiError } from "./api";
import type { PermissionKey, Role, User } from "./types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const HOME_ROUTES: { permission: PermissionKey; path: string }[] = [
  { permission: "dashboard", path: "/dashboard" },
  { permission: "contracts", path: "/contracts" },
  { permission: "reviews", path: "/reviews" },
  { permission: "templates", path: "/templates" },
];

export function hasPermission(user: User | null, permission: PermissionKey): boolean {
  return Boolean(user?.permissions?.includes(permission));
}

export function hasAnyPermission(user: User | null, permissions: PermissionKey[]): boolean {
  return permissions.some((permission) => hasPermission(user, permission));
}

export function homePathForUser(user: User | null): string {
  if (!user) return "/login";
  const matched = HOME_ROUTES.find((item) => hasPermission(user, item.permission));
  if (matched) return matched.path;
  if (user.role === "admin") return "/admin/permissions";
  return "/no-access";
}

export function HomeRedirect() {
  const { user } = useAuth();
  return <Navigate to={homePathForUser(user)} replace />;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    api
      .me()
      .then((result) => {
        if (active) setUser(result.user);
      })
      .catch((error: unknown) => {
        if (!(error instanceof ApiError && error.status === 401)) {
          console.error(error);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const result = await api.login(username, password);
    setUser(result.user);
    return result.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, logout }),
    [user, loading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

export function RequireAuth() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) {
    return (
      <div className="fullscreen-loader">
        <div className="brand-loader-mark">MM</div>
        <Spin size="large" />
        <span>正在载入绵绵聚道…</span>
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user } = useAuth();
  if (!user || !roles.includes(user.role)) {
    return <Navigate to={homePathForUser(user)} replace />;
  }
  return <>{children}</>;
}

export function RequirePermission({
  permissions,
  children,
}: {
  permissions: PermissionKey[];
  children: ReactNode;
}) {
  const { user } = useAuth();
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  if (!hasAnyPermission(user, permissions)) {
    return <Navigate to={homePathForUser(user)} replace />;
  }
  return <>{children}</>;
}
