import { getAuthState, signInWithGoogle, signOutUser } from "./auth.js";

// Renders the auth button (or signed-in user chip) inside the navbar slot.
function renderAuthButton(container) {
  if (!container) return;
  const state = getAuthState();

  if (state.signed_in) {
    const initial = (state.display_name || state.email || "?")[0].toUpperCase();
    const avatarHtml = state.photo_url
      ? `<img src="${state.photo_url}" class="auth-avatar" alt="profile"
             onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">`
      : "";
    const fallbackHtml = `<div class="auth-avatar-fallback" style="display:${state.photo_url ? "none" : "flex"}">${initial}</div>`;

    container.innerHTML = `
      <div class="auth-user">
        ${avatarHtml}
        ${fallbackHtml}
        <span class="auth-name">${state.display_name || state.email}</span>
        <button class="auth-signout btn btn--text" id="auth-signout-btn" type="button">Sign out</button>
      </div>`;
    document
      .getElementById("auth-signout-btn")
      ?.addEventListener("click", async () => {
        await signOutUser();
        window.location.href = "index.html";
      });
  } else {
    container.innerHTML = `
      <button class="auth-signin btn btn--text" id="auth-signin-btn" type="button">
        <svg width="18" height="18" viewBox="0 0 24 24" style="margin-right:6px;vertical-align:middle">
          <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
          <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
          <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
          <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
        </svg>
        Sign in with Google
      </button>`;
    document
      .getElementById("auth-signin-btn")
      ?.addEventListener("click", async () => {
        await signInWithGoogle();
      });
  }
}

// Yellow guest banner — shown to guests on Watch and Account pages.
// Re-runs cleanly on every auth state change: clears any stale banner DOM
// before hiding (so a flicker between signed-in and signed-out states
// can't leave a half-rendered banner lingering in the document).
function renderGuestBanner(container, message) {
  if (!container) return;
  const state = getAuthState();
  if (state.signed_in) {
    container.innerHTML = "";
    container.style.display = "none";
    return;
  }
  container.style.display = "block";
  container.innerHTML = `
    <div class="guest-banner">
      <span>${message || "You're browsing as a guest. Sign in to save your history across sessions."}</span>
      <button class="btn btn--text guest-banner__signin" id="guest-banner-signin" type="button">Sign in with Google</button>
    </div>`;
  document
    .getElementById("guest-banner-signin")
    ?.addEventListener("click", async () => {
      // Lazy import per Step's spec: avoids a top-level dependency cycle that
      // could fire before Firebase finishes restoring its persisted session.
      const { signInWithGoogle: signIn } = await import("./auth.js");
      await signIn();
    });
}

export { renderAuthButton, renderGuestBanner };
