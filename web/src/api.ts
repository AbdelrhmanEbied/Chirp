const BASE = '/api/v1';

class ApiClient {
  private token: string | null = null;

  setToken(token: string | null) {
    this.token = token;
    if (token) {
      localStorage.setItem('token', token);
    } else {
      localStorage.removeItem('token');
    }
  }

  getToken(): string | null {
    if (!this.token) {
      this.token = localStorage.getItem('token');
    }
    return this.token;
  }

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const token = this.getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    if (response.status === 401) {
      this.setToken(null);
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error?.error?.message || `Request failed: ${response.status}`);
    }

    if (response.status === 204) return undefined as T;
    return response.json();
  }

  // Auth
  async register(data: { email: string; username: string; display_name: string; password: string }) {
    const result = await this.request<{ access_token: string; user_id: string }>('POST', '/auth/register', data);
    this.setToken(result.access_token);
    return result;
  }

  async login(data: { email: string; password: string }) {
    const result = await this.request<{ access_token: string; user_id: string }>('POST', '/auth/login', data);
    this.setToken(result.access_token);
    return result;
  }

  async getMe() {
    return this.request<{ id: string; username: string; display_name: string; email: string }>('GET', '/users/me');
  }

  // Posts
  async createPost(text: string, replyToId?: string) {
    return this.request<{ id: string; text: string; author_id: string; created_at: string }>('POST', '/posts', { text, reply_to_id: replyToId });
  }

  async getPost(id: string) {
    return this.request<{ id: string; author_id: string; text: string; likes_count: number; reposts_count: number; replies_count: number; created_at: string; liked_by_me: boolean; reposted_by_me: boolean }>('GET', `/posts/${id}`);
  }

  async deletePost(id: string) {
    await this.request<void>('DELETE', `/posts/${id}`);
  }

  async likePost(id: string) {
    await this.request<void>('POST', `/posts/${id}/like`);
  }

  async unlikePost(id: string) {
    await this.request<void>('DELETE', `/posts/${id}/like`);
  }

  async repost(id: string) {
    await this.request<void>('POST', `/posts/${id}/repost`);
  }

  async unrepost(id: string) {
    await this.request<void>('DELETE', `/posts/${id}/repost`);
  }

  async getUserPosts(authorId: string, limit = 20) {
    return this.request<Array<{ id: string; author_id: string; text: string; likes_count: number; reposts_count: number; replies_count: number; created_at: string }>>('GET', `/posts/by/${authorId}?limit=${limit}`);
  }

  async getReplies(postId: string) {
    return this.request<Array<{ id: string; author_id: string; text: string; likes_count: number; created_at: string }>>('GET', `/posts/${postId}/replies`);
  }

  // Timeline
  async getHomeFeed(limit = 20, cursor?: string) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) params.set('cursor', cursor);
    return this.request<{ entries: Array<{ post_id: string; author_id: string; text: string; likes_count: number; reposts_count: number; replies_count: number; created_at: string; author_name: string; author_username: string }>; next_cursor: string | null; has_more: boolean }>('GET', `/timeline/home?${params}`);
  }

  async getUserTimeline(userId: string, limit = 20) {
    return this.request<{ entries: Array<{ post_id: string; author_id: string; text: string; likes_count: number; created_at: string; author_name: string; author_username: string }>; has_more: boolean }>('GET', `/timeline/user/${userId}?limit=${limit}`);
  }

  // Users
  async getUserProfile(username: string) {
    return this.request<{ id: string; username: string; display_name: string; bio: string | null; followers_count: number; following_count: number; posts_count: number }>('GET', `/users/username/${username}`);
  }

  async updateProfile(data: { display_name?: string; bio?: string }) {
    return this.request<unknown>('PATCH', '/users/me', data);
  }

  // Graph
  async follow(userId: string) {
    await this.request<void>('POST', `/graph/follow/${userId}`);
  }

  async unfollow(userId: string) {
    await this.request<void>('DELETE', `/graph/follow/${userId}`);
  }

  async getFollowers(userId: string) {
    return this.request<Array<{ id: string; username: string; display_name: string }>>('GET', `/graph/${userId}/followers`);
  }

  async getFollowing(userId: string) {
    return this.request<Array<{ id: string; username: string; display_name: string }>>('GET', `/graph/${userId}/following`);
  }

  // Search
  async searchPosts(query: string) {
    return this.request<{ results: Array<{ id: string; post_id: string; author_id: string; text: string; created_at: string }> }>('GET', `/search/posts?q=${encodeURIComponent(query)}`);
  }

  async getTrending() {
    return this.request<{ hashtags: Array<{ hashtag: string; usage_count: number }> }>('GET', '/search/trending');
  }

  // Notifications
  async getNotifications(limit = 20) {
    return this.request<{ notifications: Array<{ id: string; actor_id: string; notification_type: string; subject_id: string; is_read: boolean; created_at: string }> }>('GET', `/notifications?limit=${limit}`);
  }

  async getUnreadCount() {
    return this.request<{ count: number }>('GET', '/notifications/unread-count');
  }

  async markAllRead() {
    await this.request<void>('POST', '/notifications/read-all');
  }

  // Messaging
  async getConversations() {
    return this.request<{ conversations: Array<{ id: string; title: string | null; last_message: string | null; unread_count: number; created_at: string }> }>('GET', '/messages/conversations');
  }

  async getMessages(conversationId: string, limit = 50) {
    return this.request<{ messages: Array<{ id: string; sender_id: string; text: string; created_at: string }> }>('GET', `/messages/conversations/${conversationId}/messages?limit=${limit}`);
  }

  async sendMessage(conversationId: string, text: string) {
    return this.request<{ id: string; text: string; sender_id: string }>('POST', `/messages/conversations/${conversationId}/messages`, { text });
  }

  async createConversation(participantIds: string[]) {
    return this.request<{ id: string }>('POST', '/messages/conversations', { participant_ids: participantIds });
  }

  // Media
  async uploadMedia(file: File) {
    const formData = new FormData();
    formData.append('file', file);
    const token = this.getToken();
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const response = await fetch(`${BASE}/media`, { method: 'POST', headers, body: formData });
    if (!response.ok) throw new Error('Upload failed');
    return response.json();
  }
}

export const api = new ApiClient();
