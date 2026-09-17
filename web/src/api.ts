const MOCK_USER = {
  id: 'user-1',
  username: 'chirpuser',
  display_name: 'Chirp User',
  email: 'user@chirp.dev',
  bio: 'Just vibing on Chirp.',
  avatar_url: '',
  followers_count: 42,
  following_count: 17,
  posts_count: 8,
};

const MOCK_USERS: Record<string, typeof MOCK_USER> = {
  chirpuser: MOCK_USER,
  alice: { id: 'user-2', username: 'alice', display_name: 'Alice Chen', email: 'alice@chirp.dev', bio: 'Full-stack dev. I build things with TypeScript and Go.', avatar_url: '', followers_count: 120, following_count: 80, posts_count: 34 },
  bob: { id: 'user-3', username: 'bob', display_name: 'Bob Smith', email: 'bob@chirp.dev', bio: 'Open source enthusiast. Rust evangelist.', avatar_url: '', followers_count: 55, following_count: 40, posts_count: 12 },
  carol: { id: 'user-4', username: 'carol', display_name: 'Carol Davis', email: 'carol@chirp.dev', bio: 'Designer & maker. Pixels are my playground.', avatar_url: '', followers_count: 200, following_count: 150, posts_count: 67 },
};

const now = new Date().toISOString();
const hourAgo = new Date(Date.now() - 3600000).toISOString();
const dayAgo = new Date(Date.now() - 86400000).toISOString();

const MOCK_POSTS = [
  { post_id: 'p1', author_id: 'user-2', text: 'Just shipped a new feature! 🚀 The timeline service is now fully event-driven.', likes_count: 24, reposts_count: 5, replies_count: 3, created_at: hourAgo, author_name: 'Alice Chen', author_username: 'alice' },
  { post_id: 'p2', author_id: 'user-3', text: 'Working on a cool side project using Rust and WebAssembly. Stay tuned!', likes_count: 18, reposts_count: 2, replies_count: 1, created_at: now, author_name: 'Bob Smith', author_username: 'bob' },
  { post_id: 'p3', author_id: 'user-4', text: 'Design tip: white space is not empty space. It gives your content room to breathe.', likes_count: 67, reposts_count: 12, replies_count: 8, created_at: dayAgo, author_name: 'Carol Davis', author_username: 'carol' },
  { post_id: 'p4', author_id: 'user-2', text: 'Hot take: microservices are great when you actually need them. Don\'t over-engineer your side projects.', likes_count: 45, reposts_count: 9, replies_count: 14, created_at: dayAgo, author_name: 'Alice Chen', author_username: 'alice' },
  { post_id: 'p5', author_id: 'user-1', text: 'Hello world! This is my first post on Chirp. Excited to be here!', likes_count: 5, reposts_count: 0, replies_count: 2, created_at: now, author_name: 'Chirp User', author_username: 'chirpuser' },
];

let postIdCounter = 10;
let notifIdCounter = 10;
let convIdCounter = 10;

export type MockUser = typeof MOCK_USER;

class MockApiClient {
  private token: string | null = 'mock-jwt-token';

  setToken(token: string | null) {
    this.token = token;
    if (token) localStorage.setItem('token', token);
    else localStorage.removeItem('token');
  }

  getToken(): string | null {
    if (!this.token) this.token = localStorage.getItem('token');
    return this.token;
  }

  async register(data: { email: string; username: string; display_name: string; password: string }) {
    MOCK_USER.username = data.username;
    MOCK_USER.display_name = data.display_name;
    MOCK_USER.email = data.email;
    MOCK_USERS[data.username] = MOCK_USER;
    return { access_token: 'mock-jwt-token', user_id: MOCK_USER.id };
  }

  async login(_data: { email: string; password: string }) {
    return { access_token: 'mock-jwt-token', user_id: MOCK_USER.id };
  }

  async getMe() {
    return { ...MOCK_USER };
  }

  async createPost(text: string, _replyToId?: string) {
    const id = `p${++postIdCounter}`;
    const newPost = { id, author_id: MOCK_USER.id, text, likes_count: 0, reposts_count: 0, replies_count: 0, created_at: new Date().toISOString(), liked_by_me: false, reposted_by_me: false };
    MOCK_POSTS.unshift({ ...newPost, post_id: id, author_name: MOCK_USER.display_name, author_username: MOCK_USER.username });
    return newPost;
  }

  async getPost(id: string) {
    const p = MOCK_POSTS.find(p => p.post_id === id);
    return { id: p?.post_id || id, author_id: p?.author_id || MOCK_USER.id, text: p?.text || 'Post not found', likes_count: p?.likes_count || 0, reposts_count: p?.reposts_count || 0, replies_count: p?.replies_count || 0, created_at: p?.created_at || now, liked_by_me: false, reposted_by_me: false };
  }

  async deletePost(_id: string) {}

  async likePost(id: string) {
    const p = MOCK_POSTS.find(p => p.post_id === id);
    if (p) p.likes_count++;
  }

  async unlikePost(id: string) {
    const p = MOCK_POSTS.find(p => p.post_id === id);
    if (p) p.likes_count = Math.max(0, p.likes_count - 1);
  }

  async repost(id: string) {
    const p = MOCK_POSTS.find(p => p.post_id === id);
    if (p) p.reposts_count++;
  }

  async unrepost(id: string) {
    const p = MOCK_POSTS.find(p => p.post_id === id);
    if (p) p.reposts_count = Math.max(0, p.reposts_count - 1);
  }

  async getUserPosts(authorId: string, _limit = 20) {
    return MOCK_POSTS.filter(p => p.author_id === authorId).map(p => ({
      id: p.post_id, author_id: p.author_id, text: p.text, likes_count: p.likes_count,
      reposts_count: p.reposts_count, replies_count: p.replies_count, created_at: p.created_at,
    }));
  }

  async getReplies(_postId: string) {
    return [
      { id: 'r1', author_id: 'user-3', text: 'Great point! Totally agree.', likes_count: 3, created_at: now },
      { id: 'r2', author_id: 'user-4', text: 'Thanks for sharing this 🙌', likes_count: 1, created_at: hourAgo },
    ];
  }

  async getHomeFeed(limit = 20, _cursor?: string) {
    return { entries: MOCK_POSTS.slice(0, limit), next_cursor: null, has_more: false };
  }

  async getUserTimeline(_userId: string, limit = 20) {
    return { entries: MOCK_POSTS.slice(0, limit), has_more: false };
  }

  async getUserProfile(username: string) {
    const user = MOCK_USERS[username];
    return user ? { ...user } : { ...MOCK_USER };
  }

  async updateProfile(data: { display_name?: string; bio?: string; avatar_url?: string }) {
    if (data.display_name !== undefined) MOCK_USER.display_name = data.display_name;
    if (data.bio !== undefined) MOCK_USER.bio = data.bio;
    if (data.avatar_url !== undefined) MOCK_USER.avatar_url = data.avatar_url;
    return { ...MOCK_USER };
  }

  async follow(_userId: string) {}
  async unfollow(_userId: string) {}
  async getFollowers(_userId: string) { return []; }
  async getFollowing(_userId: string) { return []; }

  async searchPosts(query: string) {
    return { results: MOCK_POSTS.filter(p => p.text.toLowerCase().includes(query.toLowerCase())).map(p => ({ id: p.post_id, post_id: p.post_id, author_id: p.author_id, text: p.text, created_at: p.created_at })) };
  }

  async getTrending() {
    return { hashtags: [
      { hashtag: 'rust', usage_count: 234 },
      { hashtag: 'webdev', usage_count: 189 },
      { hashtag: 'opensource', usage_count: 156 },
      { hashtag: 'design', usage_count: 142 },
      { hashtag: 'microservices', usage_count: 98 },
    ]};
  }

  async getNotifications(limit = 20) {
    return { notifications: [
      { id: `n${++notifIdCounter}`, actor_id: 'user-2', notification_type: 'post_liked', subject_id: 'p5', is_read: false, created_at: now },
      { id: `n${++notifIdCounter}`, actor_id: 'user-3', notification_type: 'user_followed', subject_id: 'user-1', is_read: false, created_at: hourAgo },
      { id: `n${++notifIdCounter}`, actor_id: 'user-4', notification_type: 'reply_created', subject_id: 'p5', is_read: true, created_at: dayAgo },
    ].slice(0, limit) };
  }

  async getUnreadCount() { return { count: 2 }; }

  async markAllRead() {}

  async getConversations() {
    return { conversations: [
      { id: `c${++convIdCounter}`, title: 'Alice Chen', last_message: 'Hey, nice post!', unread_count: 1, created_at: hourAgo },
      { id: `c${++convIdCounter}`, title: 'Bob Smith', last_message: 'Let me know when you want to pair program', unread_count: 0, created_at: dayAgo },
    ]};
  }

  async getMessages(_conversationId: string, _limit = 50) {
    return { messages: [
      { id: 'm1', sender_id: 'user-2', text: 'Hey! Loved your latest post.', created_at: hourAgo },
      { id: 'm2', sender_id: 'user-1', text: 'Thanks! Was fun to write.', created_at: new Date(Date.now() - 1800000).toISOString() },
      { id: 'm3', sender_id: 'user-2', text: 'We should collab sometime.', created_at: new Date(Date.now() - 900000).toISOString() },
    ]};
  }

  async sendMessage(_conversationId: string, text: string) {
    return { id: `m${Date.now()}`, text, sender_id: MOCK_USER.id };
  }

  async createConversation(_participantIds: string[]) {
    return { id: `c${++convIdCounter}` };
  }

  async uploadMedia(file: File) {
    const dataUrl = await new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.readAsDataURL(file);
    });
    return { id: `media-${Date.now()}`, url: dataUrl, content_type: file.type, size_bytes: file.size };
  }
}

export const api = new MockApiClient();
