import { Link } from 'react-router-dom';

interface Post {
  id: string;
  author_id: string;
  text: string;
  likes_count: number;
  reposts_count?: number;
  replies_count?: number;
  created_at: string;
  liked_by_me?: boolean;
  reposted_by_me?: boolean;
  author_name?: string;
  author_username?: string;
  author_avatar?: string;
}

interface PostCardProps {
  post: Post;
  onLike?: (id: string) => void;
  onRepost?: (id: string) => void;
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
}

function getInitials(name: string): string {
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2);
}

function getAvatarColor(name: string): string {
  const colors = ['#1d9bf0', '#f91880', '#00ba7c', '#7856ff', '#ff7a00', '#00ba7c'];
  let hash = 0;
  for (const c of name) hash = c.charCodeAt(0) + ((hash << 5) - hash);
  return colors[Math.abs(hash) % colors.length];
}

function AuthorAvatar({ name, avatarUrl, size = 40 }: { name: string; avatarUrl?: string; size?: number }) {
  if (avatarUrl) {
    return <img src={avatarUrl} alt={name} style={{ width: size, height: size, borderRadius: '50%', objectFit: 'cover' }} />;
  }
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%',
      background: getAvatarColor(name),
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      color: 'white', fontWeight: 700, fontSize: size * 0.4,
      flexShrink: 0,
    }}>
      {getInitials(name)}
    </div>
  );
}

export { AuthorAvatar };

export default function PostCard({ post, onLike, onRepost }: PostCardProps) {
  const displayName = post.author_name || post.author_id;
  return (
    <div className="post-card">
      <div className="post-card-header">
        <Link to={`/profile/${post.author_username || post.author_id}`}>
          <AuthorAvatar name={displayName} avatarUrl={post.author_avatar} size={40} />
        </Link>
        <div className="post-card-meta">
          <div>
            <Link to={`/profile/${post.author_username || post.author_id}`} className="author">
              {displayName}
            </Link>
            {post.author_username && <span className="handle">@{post.author_username}</span>}
            <span className="time"> · {timeAgo(post.created_at)}</span>
          </div>
          <Link to={`/post/${post.id}`} className="text" style={{ color: 'inherit' }}>
            {post.text}
          </Link>
        </div>
      </div>
      <div className="actions">
        <Link to={`/post/${post.id}`} style={{ color: 'inherit', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
          <span>💬 {post.replies_count || 0}</span>
        </Link>
        <button
          className={post.reposted_by_me ? 'reposted' : ''}
          onClick={(e) => { e.preventDefault(); onRepost?.(post.id); }}
        >
          <span>🔁 {post.reposts_count || 0}</span>
        </button>
        <button
          className={post.liked_by_me ? 'liked' : ''}
          onClick={(e) => { e.preventDefault(); onLike?.(post.id); }}
        >
          <span>{post.liked_by_me ? '❤️' : '🤍'} {post.likes_count || 0}</span>
        </button>
      </div>
    </div>
  );
}
