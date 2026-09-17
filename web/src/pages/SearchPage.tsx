import { useState, useEffect } from 'react';
import { api } from '../api';

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Array<{ id: string; post_id: string; author_id: string; text: string; created_at: string }>>([]);
  const [trending, setTrending] = useState<Array<{ hashtag: string; usage_count: number }>>([]);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    api.getTrending().then(r => setTrending(r.hashtags)).catch(() => {});
  }, []);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    try {
      const r = await api.searchPosts(query);
      setResults(r.results);
    } catch { /* empty */ }
    setSearching(false);
  };

  return (
    <div>
      <div className="header">Search</div>
      <form onSubmit={handleSearch} style={{ padding: '1rem', borderBottom: '1px solid var(--border)' }}>
        <input type="text" placeholder="Search posts..." value={query} onChange={e => setQuery(e.target.value)} />
      </form>
      {searching && <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-secondary)' }}>Searching...</div>}
      {results.length > 0 && results.map(r => (
        <div key={r.id} className="post-card">
          <div className="text">{r.text}</div>
        </div>
      ))}
      {!searching && query && results.length === 0 && (
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>No results found</div>
      )}
      {!query && trending.length > 0 && (
        <div>
          <div style={{ padding: '1rem', fontWeight: 700 }}>Trending</div>
          {trending.map(t => (
            <div key={t.hashtag} className="post-card">
              <span style={{ fontWeight: 700 }}>#{t.hashtag}</span>
              <span style={{ color: 'var(--text-secondary)', marginLeft: '0.5rem' }}>{t.usage_count} posts</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
