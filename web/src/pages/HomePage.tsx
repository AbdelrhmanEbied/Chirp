import { useState, useEffect, useCallback } from 'react';
import { api } from '../api';
import { useAuth } from '../hooks/useAuth';
import PostCard from '../components/PostCard';

interface Post {
  post_id: string;
  author_id: string;
  text: string;
  likes_count: number;
  reposts_count: number;
  replies_count: number;
  created_at: string;
  author_name: string;
  author_username: string;
}

export default function HomePage() {
  const { user } = useAuth();
  const [posts, setPosts] = useState<Post[]>([]);
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(true);
  const [posting, setPosting] = useState(false);

  const load = useCallback(async () => {
    try {
      const feed = await api.getHomeFeed(30);
      setPosts(feed.entries);
    } catch { /* empty */ }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handlePost = async () => {
    if (!text.trim() || posting) return;
    setPosting(true);
    try {
      await api.createPost(text);
      setText('');
      await load();
    } catch { /* empty */ }
    setPosting(false);
  };

  const handleLike = async (postId: string) => {
    try { await api.likePost(postId); await load(); } catch { /* empty */ }
  };

  const handleRepost = async (postId: string) => {
    try { await api.repost(postId); await load(); } catch { /* empty */ }
  };

  return (
    <div>
      <div className="header">Home</div>
      <div className="composer">
        <textarea placeholder="What's happening?" value={text} onChange={e => setText(e.target.value)} />
      </div>
      <div style={{ padding: '0.5rem 1rem', borderBottom: '1px solid var(--border)' }}>
        <button className="btn-primary" onClick={handlePost} disabled={!text.trim() || posting}>
          {posting ? 'Posting...' : 'Post'}
        </button>
      </div>
      {loading ? (
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>Loading feed...</div>
      ) : posts.length === 0 ? (
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
          No posts yet. Follow some people to see their posts here!
        </div>
      ) : (
        posts.map(p => (
          <PostCard key={p.post_id} post={{ ...p, id: p.post_id }} onLike={handleLike} onRepost={handleRepost} />
        ))
      )}
    </div>
  );
}
