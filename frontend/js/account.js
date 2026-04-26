/**
 * account.js — Account page logic.
 * Fetches /api/account/me and populates the static row layout.
 */

async function loadAccount() {
  try {
    const res = await fetch("/api/account/me");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    document.getElementById("account-email").textContent = data.email || "—";
    document.getElementById("account-watches").textContent =
      data.active_watches ?? "—";
    document.getElementById("account-matches").textContent =
      data.matches_run ?? "—";
  } catch (e) {
    console.error("Failed to load account:", e);
  }
}

document.addEventListener("DOMContentLoaded", loadAccount);
