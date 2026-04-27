/**
 * account.js — Account page logic.
 *
 * Pulls counts from /api/account/me with the user's auth header so the
 * server can scope them. Email is sourced from the Firebase auth state
 * (when signed in) so it always matches the current Google account, even
 * if the backend hasn't been wired to per-user identity yet.
 */

import { auth, onAuthStateChanged, getAuthState, getAuthHeader } from "./auth.js";

async function loadAccount() {
  const state = getAuthState();

  // Email always comes from Firebase for signed-in users.
  document.getElementById("account-email").textContent = state.signed_in
    ? state.email
    : "guestuser@domain.com";

  try {
    const authHeader = await getAuthHeader();
    const res = await fetch("/api/account/me", {
      headers: { Authorization: authHeader },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    document.getElementById("account-watches").textContent =
      data.active_watches ?? "—";
    document.getElementById("account-matches").textContent =
      data.matches_run ?? "—";
  } catch (e) {
    console.error("Failed to load account:", e);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadAccount();
  // Re-render account fields on every auth-state change so signing in/out
  // updates the page without needing a manual reload.
  onAuthStateChanged(auth, () => {
    loadAccount();
  });
});
