import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../api';
import PostCard from '../components/PostCard';
import { AuthorAvatar } from '../components/PostCard';
import { useAuth } from '../hooks/useAuth';

export default function ProfilePage() {
  const { username } = useParams<{ username: string }>();
  const { user: currentUser } = useAuth();
  const [profile, setProfile] = useState<{ id: string; username: string; display_name: string; bio: string | null; avatar_url: string; followers_count: number; following_count: number; posts_count: number } | null>(null);
  const [posts, setPosts] = useState<Array<{ id: string; author_id: string; text: string; likes_count: number; reposts_count: number; replies_count: number; created_at: string }>>([]);
  const [loading, setLoading] = useState(true);

  const isOwnProfile = currentUser?.username === username;

  const load = useCallback(async () => {
    if (!username) return;
    try {
      const p = await api.getUserProfile(username);
      setProfile(p);
      const userPosts = await api.getUserPosts(p.id);
      setPosts(userPosts);
    } catch { /* empty */ }
    setLoading(false);
  }, [username]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div style={{ padding: '2rem', textAlign: 'center' }}>Loading profile...</div>;
  if (!profile) return <div style={{ padding: '2rem', textAlign: 'center' }}>User not found</div>;

  return (
    <div>
      <div className="header">{profile.display_name}</div>
      <div className="profile-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <AuthorAvatar name={profile.display_name} avatarUrl={profile.avatar_url} size={80} />
          {isOwnProfile ? (
            <Link to="/settings/profile" className="btn-outline" style={{ fontSize: '0.85rem', padding: '0.4rem 1rem', textDecoration: 'none' }}>
              Edit profile
            </Link>
          ) : (
            <button className="btn-primary" style={{ fontSize: '0.85rem', padding: '0.4rem 1.5rem' }}>Follow</button>
          )}
        </div>
        <div className="name" style={{ marginTop: '0.75rem' }}>{profile.display_name}</div>
        <div className="handle">@{username}</div>
        {profile.bio && <div className="bio" style={{ marginTop: '0.5rem' }}>{profile.bio}</div>}
        <div className="stats" style={{ marginTop: '0.75rem' }}>
          <span><strong>{profile.following_count}</strong> Following</span>
          <span><strong>{profile.followers_count}</strong> Followers</span>
          <span><strong>{profile.posts_count}</strong> Posts</span>
        </div>
      </div>
      {posts.map(p => (
        <PostCard key={p.id} post={p} />
      ))}
      {posts.length === 0 && (
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
          No posts yet.
        </div>
      )}
    </div>
  );
}
