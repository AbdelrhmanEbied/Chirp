import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../api';
import PostCard from '../components/PostCard';

export default function ProfilePage() {
  const { username } = useParams<{ username: string }>();
  const [profile, setProfile] = useState<{ id: string; display_name: string; bio: string | null; followers_count: number; following_count: number; posts_count: number } | null>(null);
  const [posts, setPosts] = useState<Array<{ id: string; author_id: string; text: string; likes_count: number; reposts_count: number; replies_count: number; created_at: string }>>([]);
  const [loading, setLoading] = useState(true);

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
        <div className="name">{profile.display_name}</div>
        <div className="handle">@{username}</div>
        {profile.bio && <div className="bio">{profile.bio}</div>}
        <div className="stats">
          <span><strong>{profile.following_count}</strong> Following</span>
          <span><strong>{profile.followers_count}</strong> Followers</span>
          <span><strong>{profile.posts_count}</strong> Posts</span>
        </div>
      </div>
      {posts.map(p => (
        <PostCard key={p.id} post={p} />
      ))}
    </div>
  );
}
