import { Link } from 'react-router-dom';

interface Post {
  id: string;
  author_id: string;
  text: string;
  likes_count: number;
  reposts_count: number;
  replies_count: number;
  created_at: string;
  liked_by_me?: boolean;
  reposted_by_me?: boolean;
  author_name?: string;
  author_username?: string;
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

export default function PostCard({ post, onLike, onRepost }: PostCardProps) {
  return (
    <div className="post-card">
      <div>
        <Link to={`/profile/${post.author_username || post.author_id}`} className="author">
          {post.author_name || post.author_id}
        </Link>
        {post.author_username && <span className="handle">@{post.author_username}</span>}
        <span className="time"> · {timeAgo(post.created_at)}</span>
      </div>
      <Link to={`/post/${post.id}`} className="text" style={{ color: 'inherit' }}>
        {post.text}
      </Link>
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
