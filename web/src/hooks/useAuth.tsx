import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';
import { api } from '../api';

interface AuthState {
  isAuthenticated: boolean;
  loading: boolean;
  user: { id: string; username: string; display_name: string } | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, username: string, displayName: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthState['user']>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const token = api.getToken();
      if (!token) { setUser(null); return; }
      const me = await api.getMe();
      setUser({ id: me.id, username: me.username, display_name: me.display_name });
    } catch {
      setUser(null);
      api.setToken(null);
    }
  }, []);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  const login = async (email: string, password: string) => {
    await api.login({ email, password });
    await refresh();
  };

  const register = async (email: string, username: string, displayName: string, password: string) => {
    await api.register({ email, username, display_name: displayName, password });
    await refresh();
  };

  const logout = () => {
    api.setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ isAuthenticated: !!user, loading, user, login, register, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
