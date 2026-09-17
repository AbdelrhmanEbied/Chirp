import { useState, useEffect, useCallback } from 'react';
import { api } from '../api';

interface Conversation {
  id: string;
  title: string | null;
  last_message: string | null;
  unread_count: number;
  created_at: string;
}

interface Message {
  id: string;
  sender_id: string;
  text: string;
  created_at: string;
}

export default function MessagesPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [newMessage, setNewMessage] = useState('');
  const [loading, setLoading] = useState(true);

  const loadConversations = useCallback(async () => {
    try {
      const r = await api.getConversations();
      setConversations(r.conversations);
    } catch { /* empty */ }
    setLoading(false);
  }, []);

  useEffect(() => { loadConversations(); }, [loadConversations]);

  const loadMessages = async (convId: string) => {
    setSelectedId(convId);
    try {
      const r = await api.getMessages(convId);
      setMessages(r.messages);
    } catch { /* empty */ }
  };

  const handleSend = async () => {
    if (!newMessage.trim() || !selectedId) return;
    try {
      await api.sendMessage(selectedId, newMessage);
      setNewMessage('');
      await loadMessages(selectedId);
    } catch { /* empty */ }
  };

  if (loading) return <div style={{ padding: '2rem', textAlign: 'center' }}>Loading...</div>;

  if (selectedId) {
    return (
      <div>
        <div className="header" style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <button className="btn-outline" onClick={() => setSelectedId(null)} style={{ padding: '0.25rem 0.5rem' }}>← Back</button>
          <span>Conversation</span>
        </div>
        <div style={{ padding: '1rem', maxHeight: '60vh', overflowY: 'auto' }}>
          {messages.map(m => (
            <div key={m.id} style={{ marginBottom: '0.75rem' }}>
              <div style={{ fontWeight: 700, fontSize: '0.85rem' }}>{m.sender_id}</div>
              <div>{m.text}</div>
            </div>
          ))}
        </div>
        <div style={{ padding: '1rem', borderTop: '1px solid var(--border)', display: 'flex', gap: '0.5rem' }}>
          <input placeholder="Type a message..." value={newMessage} onChange={e => setNewMessage(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSend()} />
          <button className="btn-primary" onClick={handleSend} disabled={!newMessage.trim()}>Send</button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="header">Messages</div>
      {conversations.length === 0 ? (
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>No conversations yet</div>
      ) : (
        conversations.map(c => (
          <div key={c.id} className="conversation-item" onClick={() => loadMessages(c.id)}>
            <div className="name">{c.title || c.id}</div>
            <div className="preview">{c.last_message || 'No messages yet'}</div>
          </div>
        ))
      )}
    </div>
  );
}
