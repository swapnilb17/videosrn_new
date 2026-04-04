"use client";

import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type AuthState = {
  isAuthenticated: boolean;
  userName: string;
  credits: number;
  login: (name: string) => void;
  logout: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

const STORAGE_KEY = "enably-auth";

function getInitialAuthState() {
  if (typeof window === "undefined") {
    return {
      isAuthenticated: false,
      userName: "Alex",
      credits: 120,
    };
  }

  const stored = localStorage.getItem(STORAGE_KEY);
  if (!stored) {
    return {
      isAuthenticated: false,
      userName: "Alex",
      credits: 120,
    };
  }

  try {
    const parsed = JSON.parse(stored) as {
      isAuthenticated: boolean;
      userName: string;
      credits: number;
    };
    return parsed;
  } catch {
    localStorage.removeItem(STORAGE_KEY);
    return {
      isAuthenticated: false,
      userName: "Alex",
      credits: 120,
    };
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState(getInitialAuthState);

  const value = useMemo(
    () => ({
      isAuthenticated: state.isAuthenticated,
      userName: state.userName,
      credits: state.credits,
      login: (name: string) => {
        const nextName = name.trim() || "Alex";
        const nextState = {
          isAuthenticated: true,
          userName: nextName,
          credits: 120,
        };
        setState(nextState);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(nextState));
      },
      logout: () => {
        setState({
          isAuthenticated: false,
          userName: "Alex",
          credits: 120,
        });
        localStorage.removeItem(STORAGE_KEY);
      },
    }),
    [state],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider.");
  }
  return context;
}
