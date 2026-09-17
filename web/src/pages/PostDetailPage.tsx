import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../api';
import PostCard from '../components/PostCard';

export default function PostDetailPage() {
  const { postId } = useParams<{ postId: string }>();
  const [post, setPost] = useState<{ id: string; author_id: string; text: string; likes_count: number; reposts_count: number; replies_count: number; created_at: string; liked_by_me: boolean; reposted_by_me: boolean } | null>(null);
  const [replies, setReplies] = useState<Array<{ id: string; author_id: string; text: string; likes_count: number; reposts_count: number; replies_count: number; created_at: string }>>([]);
  const [replyText, setReplyText] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!postId) return;
    try {
      const p = await api.getPost(postId);
      setPost(p);
      const r = await api.getReplies(postId);
      setReplies(r);
    } catch { /* empty */ }
    setLoading(false);
  }, [postId]);

  useEffect(() => { load(); }, [load]);

  const handleReply = async () => {
    if (!replyText.trim() || !postId) return;
    try {
      await api.createPost(replyText, postId);
      setReplyText('');
      await load();
    } catch { /* empty */ }
  };

  const handleLike = async (id: string) => {
    try { await api.likePost(id); await load(); } catch { /* empty */ }
  };

  if (loading) return <div style={{ padding: '2rem', textAlign: 'center' }}>Loading...</div>;
  if (!post) return <div style={{ padding: '2rem', textAlign: 'center' }}>Post not found</div>;

  return (
    <div>
      <div className="header">Post</div>
      <PostCard post={post} onLike={handleLike} />
      <div className="composer">
        <textarea placeholder="Post your reply" value={replyText} onChange={e => setReplyText(e.target.value)} />
      </div>
      <div style={{ padding: '0.5rem 1rem', borderBottom: '1px solid var(--border)' }}>
        <button className="btn-primary" onClick={handleReply} disabled={!replyText.trim()}>Reply</button>
      </div>
      {replies.map(r => (
        <PostCard key={r.id} post={r} onLike={handleLike} />
      ))}
    </div>
  );
}
