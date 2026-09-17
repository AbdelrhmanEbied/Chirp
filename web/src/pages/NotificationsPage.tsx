import { useState, useEffect, useCallback } from 'react';
import { api } from '../api';

interface Notification {
  id: string;
  actor_id: string;
  notification_type: string;
  subject_id: string;
  is_read: boolean;
  created_at: string;
}

function notifText(type: string): string {
  switch (type) {
    case 'post_liked': return 'liked your post';
    case 'reply_created': return 'replied to your post';
    case 'quote_created': return 'quoted your post';
    case 'user_followed': return 'followed you';
    case 'user_mentioned': return 'mentioned you';
    case 'message_sent': return 'sent you a message';
    default: return 'interacted with you';
  }
}

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const r = await api.getNotifications(50);
      setNotifications(r.notifications);
    } catch { /* empty */ }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleMarkAllRead = async () => {
    await api.markAllRead();
    await load();
  };

  if (loading) return <div style={{ padding: '2rem', textAlign: 'center' }}>Loading...</div>;

  return (
    <div>
      <div className="header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>Notifications</span>
        <button className="btn-outline" onClick={handleMarkAllRead} style={{ fontSize: '0.8rem', padding: '0.25rem 0.75rem' }}>Mark all read</button>
      </div>
      {notifications.length === 0 ? (
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>No notifications yet</div>
      ) : (
        notifications.map(n => (
          <div key={n.id} className={`notification-item ${n.is_read ? '' : 'unread'}`}>
            <div className="icon">🔔</div>
            <div>
              <span style={{ fontWeight: 700 }}>{n.actor_id}</span> {notifText(n.notification_type)}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
