// The owner's login session, shared with every page through React context.
//
// The JWT and its expiry time are kept in localStorage so a page refresh keeps the owner
// logged in. Trade-off: JavaScript can read localStorage, so an XSS bug could steal the token.
// We reduce that risk (no raw HTML anywhere, a strict CSP, a 30-minute token) but an httpOnly
// cookie would be safer; it needs a backend change and is listed as a known limitation.
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { getMe, login as loginRequest } from "@/api/auth";
import { setUnauthorizedHandler } from "@/api/client";

const STORAGE_KEY = "warmline.auth";
export const EXPIRED_NOTICE = "Your session expired, please log in again.";

const AuthContext = createContext(null);

// A saved session is used only if it is well-formed and not expired; anything else is removed.
function loadSavedSession() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (saved?.token && saved.expiresAt > Date.now()) return saved;
  } catch {
    // Unreadable JSON: fall through and remove it.
  }
  localStorage.removeItem(STORAGE_KEY);
  return null;
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(loadSavedSession);
  const [account, setAccount] = useState(null); // {id, email, business_name} once confirmed
  const [checkError, setCheckError] = useState(null); // the "who am I" check failed (not 401)
  const [checkAttempt, setCheckAttempt] = useState(0);
  const [notice, setNotice] = useState(null); // why the owner was logged out, shown on /login

  const token = session?.token ?? null;

  const logout = useCallback((reason = null) => {
    localStorage.removeItem(STORAGE_KEY);
    setSession(null);
    setAccount(null);
    setCheckError(null);
    setNotice(reason);
  }, []);

  // Any owner request that gets 401 logs out with the "session expired" notice.
  useEffect(() => {
    setUnauthorizedHandler(() => logout(EXPIRED_NOTICE));
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  // Log out at the exact moment the token expires, even if the owner is idle.
  useEffect(() => {
    if (!session) return;
    const timer = setTimeout(() => logout(EXPIRED_NOTICE), session.expiresAt - Date.now());
    return () => clearTimeout(timer);
  }, [session, logout]);

  // A token found in storage is checked once with the server before the dashboard opens.
  // A 401 here is handled by the logout handler above.
  useEffect(() => {
    if (!token || account) return;
    let cancelled = false;
    getMe(token).then(
      (me) => {
        if (!cancelled) setAccount(me);
      },
      (error) => {
        if (!cancelled && error.status !== 401) setCheckError(error);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [token, account, checkAttempt]);

  function retryCheck() {
    setCheckError(null);
    setCheckAttempt((count) => count + 1);
  }

  // Throws an ApiError on failure (shown by the login form). Saves the session only after
  // "who am I" succeeded, so a half-finished login leaves nothing behind.
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

  const value = { token, account, checkError, retryCheck, notice, login, logout };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
