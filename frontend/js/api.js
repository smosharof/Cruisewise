/**
 * api.js — single fetch wrapper for all Cruisewise API calls.
 *
 * Endpoints return Pydantic models directly (no envelope). On non-2xx,
 * we throw an Error whose message is the FastAPI `detail` field if present.
 * Each function may also throw an Error with a `.status` property so callers
 * can branch on 422 / 500 etc.
 */

const BASE = "/api";

async function request(method, path, body) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body !== undefined) {
    opts.body = JSON.stringify(body);
  }

  const res = await fetch(`${BASE}${path}`, opts);
  let json = null;
  try {
    json = await res.json();
  } catch {
    if (!res.ok) {
      const err = new Error(`HTTP ${res.status}`);
      err.status = res.status;
      throw err;
    }
    return null;
  }

  if (!res.ok) {
    const detail = (json && (json.detail || json.error)) || `HTTP ${res.status}`;
    const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    err.status = res.status;
    throw err;
  }

  return json;
}

// ---------------------------------------------------------------------------
// Match
// ---------------------------------------------------------------------------
export async function submitIntake(intake) {
  return request("POST", "/match/intake", intake);
}

export async function getMatchResults(intakeId) {
  return request("GET", `/match/results/${intakeId}`);
}

// ---------------------------------------------------------------------------
// Watch
// ---------------------------------------------------------------------------
export async function registerWatch(registration) {
  return request("POST", "/watch/register", registration);
}

export async function getWatchStatus(bookingId) {
  return request("GET", `/watch/status/${bookingId}`);
}

// ---------------------------------------------------------------------------
// Booking
// ---------------------------------------------------------------------------
export async function confirmBooking(payload) {
  return request("POST", "/booking/confirm", payload);
}

// ---------------------------------------------------------------------------
// Account
// ---------------------------------------------------------------------------
export async function getMe() {
  return request("GET", "/account/me");
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------
export async function healthCheck() {
  const res = await fetch("/healthz");
  if (!res.ok) {
    const err = new Error(`HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}
