import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api';

export default function RegisterPage() {
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await api.register(email, username, displayName, password);
      navigate('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="auth-form" onSubmit={handleSubmit}>
        <h1>Create your account</h1>
        {error && <div className="error">{error}</div>}
        <input type="email" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} required />
        <input type="text" placeholder="Username" value={username} onChange={e => setUsername(e.target.value)} required minLength={3} maxLength={20} />
        <input type="text" placeholder="Display name" value={displayName} onChange={e => setDisplayName(e.target.value)} required />
        <input type="password" placeholder="Password (min 10 characters)" value={password} onChange={e => setPassword(e.target.value)} required minLength={10} />
        <button className="btn-primary" type="submit" disabled={loading}>{loading ? 'Creating account...' : 'Create account'}</button>
        <p style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </div>
  );
}
