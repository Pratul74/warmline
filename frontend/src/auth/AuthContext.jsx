import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { getMe, login as loginRequest } from "../api/auth.js";
import { setUnauthorizedHandler } from "../api/client.js";


const STORAGE_KEY = "warmline.auth";
const EXPIRED_NOTICE = "Your session expired, please log in again.";

const AuthContext = createContext(null);

function loadSavedSession() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (saved?.token && saved.expiresAt > Date.now()) return saved;
  } catch {
    
  }
  localStorage.removeItem(STORAGE_KEY);
  return null;
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(loadSavedSession);
  const [account, setAccount] = useState(null);
  const [checkError, setCheckError] = useState(null);
  const [checkAttempt, setCheckAttempt] = useState(0);
  const [notice, setNotice] = useState(null);

  const token = session?.token ?? null;

  const logout = useCallback((reason = null) => {
    localStorage.removeItem(STORAGE_KEY);
    setSession(null);
    setAccount(null);
    setCheckError(null);
    setNotice(reason);
  }, []);


  useEffect(() => {
    setUnauthorizedHandler(() => logout(EXPIRED_NOTICE));
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  useEffect(() => {
    if (!session) return;
    const timer = setTimeout(() => logout(EXPIRED_NOTICE), session.expiresAt - Date.now());
    return () => clearTimeout(timer);
  }, [session, logout]);

  useEffect(() => {
    if (!token || account) return;
    let cancelled = false;
    setCheckError(null);
    getMe(token)
      .then((me) => {
        if (!cancelled) setAccount(me);
      })
      .catch((error) => {
        if (!cancelled && error.status !== 401) setCheckError(error);
      });
    return () => {
      cancelled = true;
    };
  }, [token, account, checkAttempt]);

  async function login(email, password) {
    const result = await loginRequest({ email, password });
    const newSession = {
      token: result.access_token,
      expiresAt: Date.now() + result.expires_in * 1000,
    };
    const me = await getMe(newSession.token);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(newSession));
    setNotice(null);
    setAccount(me);
    setSession(newSession);
  }

  const value = {
    token,
    account,
    checkError,
    retryCheck: () => setCheckAttempt((n) => n + 1),
    notice,
    login,
    logout,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
