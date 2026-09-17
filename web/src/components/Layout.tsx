import { Outlet, NavLink } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

export default function Layout() {
  const { user, logout } = useAuth();

  return (
    <div className="layout">
      <aside className="sidebar">
        <div style={{ fontSize: '1.5rem', fontWeight: 700, padding: '0.75rem 1rem' }}>Chirp</div>
        <nav>
          <NavLink to="/" end>Home</NavLink>
          <NavLink to="/search">Search</NavLink>
          <NavLink to="/notifications">Notifications</NavLink>
          <NavLink to="/messages">Messages</NavLink>
          {user && <NavLink to={`/profile/${user.username}`}>Profile</NavLink>}
          <button className="btn-outline" onClick={logout} style={{ marginTop: 'auto', textAlign: 'center' }}>Log out</button>
        </nav>
      </aside>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
