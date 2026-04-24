// ── API Layer ────────────────────────────────────────────────────────────────
// Single source of truth for all backend calls.
// VITE_API_URL is set per environment:
//   Local dev:  http://localhost:8000
//   Staging:    https://python-testing-template-staging.up.railway.app
//   Production: https://python-testing-template-production.up.railway.app

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export async function getHealth() {
  try {
    const res = await fetch(`${API_URL}/health`);
    return { data: await res.json(), error: null };
  } catch {
    return { data: null, error: 'API unreachable' };
  }
}

export async function login(email, password) {
  try {
    // FastAPI's OAuth2PasswordRequestForm expects form-encoded data, not JSON.
    // The field is called "username" even though we send the email.
    const res = await fetch(`${API_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username: email, password }),
    });
    if (!res.ok) {
      const err = await res.json();
      return { data: null, error: err.detail || 'Login failed' };
    }
    return { data: await res.json(), error: null };
  } catch {
    return { data: null, error: 'API unreachable' };
  }
}

export async function getTasks(token) {
  const res = await fetch(`${API_URL}/tasks`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error('Failed to fetch tasks');
  return res.json();
}

export async function createTask(token, title, description = '') {
  const res = await fetch(`${API_URL}/tasks`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ title, description }),
  });
  if (!res.ok) throw new Error('Failed to create task');
  return res.json();
}
