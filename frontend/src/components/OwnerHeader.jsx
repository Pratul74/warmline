import { NavLink } from "react-router";
import { useAuth } from "../auth/AuthContext.jsx";
import styles from "./OwnerHeader.module.css";

// The header on every owner page: who is logged in, links between pages, log out.
export default function OwnerHeader() {
  const { account, logout } = useAuth();
  const linkClass = ({ isActive }) => (isActive ? styles.active : undefined);

  return (
    <header className={styles.header}>
      <div>
        <h1>{account.business_name}</h1>
        <p className="muted">{account.email}</p>
      </div>
      <nav className={styles.nav}>
        <NavLink to="/" end className={linkClass}>
          Integrations
        </NavLink>
        <NavLink to="/faq" className={linkClass}>
          FAQ
        </NavLink>
        <button type="button" className="secondary" onClick={() => logout()}>
          Log out
        </button>
      </nav>
    </header>
  );
}
