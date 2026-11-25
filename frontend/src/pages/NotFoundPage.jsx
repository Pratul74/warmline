import { Link } from "react-router";

export default function NotFoundPage() {
  return (
    <main className="page-center">
      <div className="card">
        <h1>Page not found</h1>
        <p className="muted">There is nothing at this address.</p>
        <Link to="/">Go to the dashboard</Link>
      </div>
    </main>
  );
}
