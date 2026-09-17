import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import { useAuth } from '../hooks/useAuth';
import { AuthorAvatar } from '../components/PostCard';

export default function EditProfilePage() {
  const { user, refresh } = useAuth();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [displayName, setDisplayName] = useState('');
  const [bio, setBio] = useState('');
  const [avatarPreview, setAvatarPreview] = useState('');
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!user) return;
    api.getUserProfile(user.username).then(profile => {
      setDisplayName(profile.display_name);
      setBio(profile.bio || '');
      setAvatarPreview(profile.avatar_url || '');
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [user]);

  const handlePhotoSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setAvatarPreview(reader.result as string);
    reader.readAsDataURL(file);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.updateProfile({
        display_name: displayName,
        bio,
        avatar_url: avatarPreview,
      });
      await refresh();
      setSuccess(true);
      setTimeout(() => setSuccess(false), 2000);
    } catch { /* empty */ }
    setSaving(false);
  };

  if (loading) return <div style={{ padding: '2rem', textAlign: 'center' }}>Loading...</div>;

  return (
    <div>
      <div className="header" style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <button className="btn-outline" onClick={() => navigate(-1)} style={{ padding: '0.25rem 0.5rem' }}>←</button>
        <span>Edit profile</span>
      </div>

      <form onSubmit={handleSubmit} style={{ padding: '1.5rem' }}>
        <div className="edit-profile-avatar-section">
          <AuthorAvatar name={displayName || 'U'} avatarUrl={avatarPreview} size={96} />
          <div>
            <button type="button" className="btn-outline" onClick={() => fileInputRef.current?.click()} style={{ fontSize: '0.85rem' }}>
              Change photo
            </button>
            <input ref={fileInputRef} type="file" accept="image/*" onChange={handlePhotoSelect} style={{ display: 'none' }} />
            {avatarPreview && (
              <button type="button" className="btn-outline" onClick={() => setAvatarPreview('')} style={{ fontSize: '0.85rem', marginLeft: '0.5rem', color: 'var(--danger)' }}>
                Remove
              </button>
            )}
          </div>
        </div>

        <div className="edit-profile-field">
          <label>Display name</label>
          <input type="text" value={displayName} onChange={e => setDisplayName(e.target.value)} required maxLength={50} />
        </div>

        <div className="edit-profile-field">
          <label>Bio</label>
          <textarea value={bio} onChange={e => setBio(e.target.value)} maxLength={160} rows={3} placeholder="Tell us about yourself" />
          <div className="char-count">{bio.length}/160</div>
        </div>

        <div style={{ marginTop: '1.5rem', display: 'flex', gap: '0.75rem' }}>
          <button type="submit" className="btn-primary" disabled={saving || !displayName.trim()}>
            {saving ? 'Saving...' : 'Save changes'}
          </button>
          <button type="button" className="btn-outline" onClick={() => navigate(-1)}>Cancel</button>
        </div>

        {success && (
          <div style={{ marginTop: '1rem', padding: '0.75rem', borderRadius: '8px', background: 'rgba(0, 186, 124, 0.15)', color: '#00ba7c', textAlign: 'center' }}>
            Profile updated!
          </div>
        )}
      </form>
    </div>
  );
}
