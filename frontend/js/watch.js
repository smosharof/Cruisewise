/**
 * watch.js — Watch page UI logic.
 *
 * On load, fetches /api/watch/list and renders one card per active watch.
 * Each card has its own Check-now / Simulate-drop buttons and result slot,
 * so per-watch actions never collide. The standalone register form is the
 * empty-state fallback (and remains usable for direct-to-Watch-page entry).
 */

import { registerWatch } from "./api.js";

const API_BASE = "/api";

function init() {
  bindRadioStyling();
  bindRegisterForm();
  bindAddFlow();
  loadAllWatches();
}

async function loadAllWatches() {
  try {
    const res = await fetch(`${API_BASE}/watch/list`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const watches = await res.json();
    if (!Array.isArray(watches) || watches.length === 0) {
      showEmptyState();
      return;
    }
    showDashboard(watches);
  } catch (e) {
    console.warn("Failed to load watch list:", e);
    showEmptyState();
  }
}

function _hideAllWrappers() {
  document.getElementById("watch-dashboard-wrapper").style.display = "none";
  document.getElementById("watch-add-wrapper").style.display = "none";
  document.getElementById("watch-empty-wrapper").style.display = "none";
}

function showEmptyState() {
  _hideAllWrappers();
  document.getElementById("watch-empty-wrapper").style.display = "";
}

function showAddWrapper() {
  _hideAllWrappers();
  document.getElementById("watch-add-wrapper").style.display = "";
  document.getElementById("watch-path-selector").style.display = "flex";
  document.getElementById("watch-manual-form-wrapper").style.display = "none";
}

function showManualForm() {
  document.getElementById("watch-path-selector").style.display = "none";
  document.getElementById("watch-manual-form-wrapper").style.display = "";
  prefillFromMatch();
}

function showDashboard(watches) {
  _hideAllWrappers();
  document.getElementById("watch-dashboard-wrapper").style.display = "";

  const container = document.getElementById("watch-status-card");
  container.innerHTML = watches.map(renderWatchCard).join("");

  watches.forEach((w) => {
    document
      .getElementById(`check-btn-${w.booking_id}`)
      ?.addEventListener("click", () => doCheck(w.booking_id));
    document
      .getElementById(`demo-btn-${w.booking_id}`)
      ?.addEventListener("click", () => doDemoDropThenCheck(w.booking_id));
    document
      .getElementById(`remove-btn-${w.booking_id}`)
      ?.addEventListener("click", () => {
        showRemoveConfirm(w.booking_id, w.ship_name || "this sailing");
      });
  });
}

function showRemoveConfirm(bookingId, shipName) {
  const card = document.getElementById(`watch-card-${bookingId}`);
  if (!card) return;

  card.querySelector(".remove-confirm")?.remove();

  const prompt = document.createElement("div");
  prompt.className = "remove-confirm";
  prompt.innerHTML = `
    <span class="remove-confirm__text">Stop watching ${escapeHtml(shipName)}?</span>
    <button class="remove-confirm__yes" type="button">Yes, remove</button>
    <button class="remove-confirm__cancel" type="button">Cancel</button>
  `;
  card.appendChild(prompt);

  prompt.querySelector(".remove-confirm__yes").addEventListener("click", async () => {
    try {
      const res = await fetch(`${API_BASE}/watch/${bookingId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      card.remove();
      if (document.querySelectorAll(".watch-card").length === 0) {
        showAddWrapper();
      }
    } catch (e) {
      prompt.remove();
      alert("Could not remove watch. Please try again.");
    }
  });

  prompt.querySelector(".remove-confirm__cancel").addEventListener("click", () => {
    prompt.remove();
  });
}

function renderWatchCard(w) {
  const id = w.booking_id;
  const ship = escapeHtml(w.ship_name || "Unknown ship");
  const line = escapeHtml(w.cruise_line || "");
  // Anchor the YYYY-MM-DD departure_date at noon local time before formatting,
  // so negative-UTC-offset timezones don't roll it back to the prior day.
  const dep = w.departure_date
    ? new Date(`${w.departure_date}T12:00:00`).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "";
  const cabin = escapeHtml(w.cabin_category || "");
  const since = formatDate(w.watching_since);
  const latestPrice =
    w.latest_price != null ? `$${formatNumber(w.latest_price)}` : "—";
  const lastChecked = w.last_checked ? formatDateTime(w.last_checked) : "Not yet checked";
  const pricePaid =
    w.price_paid_usd != null ? `$${formatNumber(w.price_paid_usd)}` : "—";
  const checks = w.checks_performed || 0;
  const repriceEvents = w.reprice_events_count || 0;

  // Synthetic sailing_ids end in "-watch" (see generateSailingId in this file)
  // and indicate a manual entry that didn't resolve to a real sailings row, so
  // price monitoring can never produce a snapshot.
  const inInventory = !w.sailing_id?.includes("-watch");

  const pricesHtml = w.latest_price
    ? `<div class="watch-card__prices">
        <span>Paid: <strong>${pricePaid}</strong></span>
        <span>Current: <strong>${latestPrice}</strong></span>
        <span class="watch-card__checked">Last checked ${escapeHtml(lastChecked)}</span>
       </div>`
    : inInventory
      ? `<div class="watch-card__prices">
          <span>Paid: <strong>${pricePaid}</strong></span>
          <span style="font-size:13px;color:var(--color-text-secondary);margin-left:8px;">
            Click <strong>Check now</strong> to fetch the current fare.
          </span>
         </div>`
      : `<div class="watch-card__prices">
          <span>Paid: <strong>${pricePaid}</strong></span>
          <span style="font-size:13px;color:#e37400;margin-left:8px;">
            This sailing isn't in our inventory yet &mdash; price monitoring unavailable.
          </span>
         </div>`;

  const simulateBtnHtml = inInventory || w.latest_price
    ? `<button class="btn btn--text btn--sm" id="demo-btn-${id}" type="button">Simulate price drop</button>`
    : "";

  return `
    <div class="watch-card" id="watch-card-${id}">
      <div class="watch-card__header">
        <div>
          <div class="watch-card__ship">${ship}</div>
          <div class="watch-card__meta">${line} · ${escapeHtml(dep)} · ${cabin}</div>
        </div>
        <div style="display:flex;align-items:center;gap:10px;">
          <span class="status-badge status-badge--active">Active</span>
          <button class="watch-card__remove" id="remove-btn-${id}" type="button"
                  title="Stop watching">Remove</button>
        </div>
      </div>
      <div class="watch-card__stats">
        <span>Watching since ${escapeHtml(since)}</span>
        <span>${checks} checks</span>
        <span>${repriceEvents} reprice events</span>
      </div>
      ${pricesHtml}
      <div class="watch-card__actions">
        <button class="btn btn--primary btn--sm" id="check-btn-${id}" type="button">Check now</button>
        ${simulateBtnHtml}
        <span class="loading" id="loading-${id}" style="display:none">
          <span class="spinner"></span>
          <span id="loading-text-${id}">Checking...</span>
        </span>
      </div>
      <div id="result-${id}"></div>
    </div>`;
}

function bindAddFlow() {
  document.getElementById("watch-add")?.addEventListener("click", () => {
    showAddWrapper();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  document.getElementById("watch-empty-add")?.addEventListener("click", () => {
    showAddWrapper();
  });
  document.getElementById("watch-add-cancel")?.addEventListener("click", () => {
    loadAllWatches();
  });
  document.getElementById("path-manual-btn")?.addEventListener("click", () => {
    showManualForm();
  });
  document.getElementById("watch-manual-back")?.addEventListener("click", () => {
    document.getElementById("watch-manual-form-wrapper").style.display = "none";
    document.getElementById("watch-path-selector").style.display = "flex";
  });
}

/* ----------------------------------------------------------------------
   Pre-fill (legacy direct-navigation path; the Match panel doesn't use it)
   ---------------------------------------------------------------------- */

function prefillFromMatch() {
  const raw = localStorage.getItem("cruisewise_watch_prefill");
  if (!raw) return;
  try {
    const s = JSON.parse(raw);
    localStorage.removeItem("cruisewise_watch_prefill");

    if (s.cruise_line) {
      const sel = document.getElementById("cruise_line");
      if (sel) sel.value = s.cruise_line;
    }
    if (s.ship_name) document.getElementById("ship_name").value = s.ship_name;
    if (s.departure_date) {
      const d = new Date(s.departure_date);
      if (!isNaN(d)) {
        document.getElementById("departure_date").value = d.toISOString().split("T")[0];
      }
    }
    if (s.cabin_category) document.getElementById("cabin_category").value = s.cabin_category;
    if (s.starting_price_usd) {
      document.getElementById("price_paid_usd").value = s.starting_price_usd;
    }

    const notice = document.getElementById("watch-prefill-notice");
    if (notice) {
      notice.textContent = `Pre-filled from your Match result: ${s.ship_name || ""} on ${s.departure_date || ""}. Review and confirm your actual price paid.`;
      notice.style.display = "block";
    }
  } catch (e) {
    console.warn("Failed to pre-fill from match:", e);
  }
}

function generateSailingId(cruiseLine, departureDate, cabinCategory) {
  const line = cruiseLine.toLowerCase().replace(/\s+/g, "-");
  const date = departureDate.replace(/-/g, "");
  const cabin = cabinCategory.charAt(0);
  return `${line}-${date}-${cabin}-watch`;
}

function bindRadioStyling() {
  document.querySelectorAll("[data-name] input[type='radio']").forEach((input) => {
    input.addEventListener("change", () => {
      document
        .querySelectorAll(`.radio-option:has(input[name="${input.name}"])`)
        .forEach((opt) => opt.classList.remove("radio-option--selected"));
      input.closest(".radio-option")?.classList.add("radio-option--selected");
    });
    if (input.checked) {
      input.closest(".radio-option")?.classList.add("radio-option--selected");
    }
  });
}

/* ----------------------------------------------------------------------
   Standalone register form (empty-state fallback)
   ---------------------------------------------------------------------- */

function bindRegisterForm() {
  const form = document.getElementById("watch-form");
  if (!form) return;
  form.addEventListener("submit", handleRegister);

  document.getElementById("cruise_line")?.addEventListener("change", async (e) => {
    clearWatchError("cruise-line");
    // The ship list depends on cruise_line, so any prior ship error is stale too.
    clearWatchError("ship-name");

    const cruiseLine = e.target.value;
    const shipSelect = document.getElementById("ship_name");
    if (!shipSelect) return;

    if (!cruiseLine) {
      shipSelect.innerHTML = '<option value="">Select cruise line first</option>';
      shipSelect.disabled = true;
      return;
    }

    shipSelect.innerHTML = '<option value="">Loading ships...</option>';
    shipSelect.disabled = true;

    try {
      const res = await fetch(`${API_BASE}/watch/ships/${encodeURIComponent(cruiseLine)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const ships = await res.json();
      if (!Array.isArray(ships) || ships.length === 0) {
        shipSelect.innerHTML = '<option value="">No ships found</option>';
        return;
      }
      const opts = ships
        .map((s) => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`)
        .join("");
      shipSelect.innerHTML = '<option value="">Select a ship</option>' + opts;
      shipSelect.disabled = false;
    } catch (err) {
      console.warn("ship lookup failed:", err);
      shipSelect.innerHTML = '<option value="">Could not load ships</option>';
    }
  });

  // Clear each field's inline error as soon as the user touches it.
  const FIELD_TO_ERROR = {
    ship_name: "ship-name",
    departure_date: "departure-date",
    cabin_category: "cabin-category",
    price_paid_usd: "price-paid",
    final_payment_date: "final-payment",
  };
  Object.entries(FIELD_TO_ERROR).forEach(([fieldId, errSlug]) => {
    const el = document.getElementById(fieldId);
    if (!el) return;
    const evt = el.tagName === "SELECT" || el.type === "date" ? "change" : "input";
    el.addEventListener(evt, () => clearWatchError(errSlug));
  });
}

const _WATCH_ERROR_SLUGS = [
  "cruise-line",
  "ship-name",
  "departure-date",
  "cabin-category",
  "price-paid",
  "final-payment",
];

function setWatchError(slug, msg) {
  const el = document.getElementById(`error-watch-${slug}`);
  if (el) el.textContent = msg;
}

function clearWatchError(slug) {
  const el = document.getElementById(`error-watch-${slug}`);
  if (el) el.textContent = "";
}

function clearAllWatchErrors() {
  _WATCH_ERROR_SLUGS.forEach(clearWatchError);
}

function collectBooking() {
  const get = (id) => document.getElementById(id).value;
  const radio = (name) =>
    document.querySelector(`[name="${name}"]:checked`)?.value || null;

  const perksRaw = get("perks_at_booking") || "";
  const perks = perksRaw
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean);

  return {
    booking_id: crypto.randomUUID(),
    user_id: "00000000-0000-0000-0000-000000000000",
    sailing_id: generateSailingId(
      get("cruise_line"),
      get("departure_date"),
      get("cabin_category"),
    ),
    cruise_line: get("cruise_line"),
    ship_name: get("ship_name"),
    departure_date: get("departure_date"),
    cabin_category: get("cabin_category"),
    cabin_number: null,
    price_paid_usd: parseInt(get("price_paid_usd"), 10),
    perks_at_booking: perks,
    booking_source: "external",
    final_payment_date: get("final_payment_date"),
    created_at: new Date().toISOString(),
  };
}

function validateWatchForm(payload) {
  let valid = true;
  clearAllWatchErrors();

  if (!payload.cruise_line) {
    setWatchError("cruise-line", "Please select a cruise line.");
    valid = false;
  }
  if (!payload.ship_name) {
    setWatchError("ship-name", "Please select a ship.");
    valid = false;
  }
  if (!payload.departure_date) {
    setWatchError("departure-date", "Please pick the departure date.");
    valid = false;
  }
  if (!payload.cabin_category) {
    setWatchError("cabin-category", "Please choose a cabin category.");
    valid = false;
  }
  if (!Number.isFinite(payload.price_paid_usd) || payload.price_paid_usd < 100) {
    setWatchError("price-paid", "Please enter the price you paid (minimum $100).");
    valid = false;
  }
  if (!payload.final_payment_date) {
    setWatchError("final-payment", "Please enter the final payment date.");
    valid = false;
  }

  if (!valid) {
    const firstError = Array.from(document.querySelectorAll(".field-error")).find(
      (el) => el.textContent.trim().length > 0,
    );
    if (firstError) firstError.scrollIntoView({ behavior: "smooth", block: "center" });
  }
  return valid;
}

async function handleRegister(e) {
  e.preventDefault();
  const submitBtn = document.getElementById("watch-submit");
  const loadingEl = document.getElementById("watch-loading");

  const booking = collectBooking();
  if (!validateWatchForm(booking)) return;

  submitBtn.disabled = true;
  loadingEl.style.display = "inline-flex";

  try {
    console.log("Watch payload:", JSON.stringify(booking));
    await registerWatch(booking);
    await loadAllWatches();
  } catch (err) {
    alert(err.message || "Failed to register watch.");
  } finally {
    submitBtn.disabled = false;
    loadingEl.style.display = "none";
  }
}

/* ----------------------------------------------------------------------
   Per-card actions
   ---------------------------------------------------------------------- */

function _setCardLoading(bookingId, on, text) {
  const loadingEl = document.getElementById(`loading-${bookingId}`);
  const loadingText = document.getElementById(`loading-text-${bookingId}`);
  const checkBtn = document.getElementById(`check-btn-${bookingId}`);
  const demoBtn = document.getElementById(`demo-btn-${bookingId}`);
  if (text && loadingText) loadingText.textContent = text;
  if (loadingEl) loadingEl.style.display = on ? "inline-flex" : "none";
  if (checkBtn) checkBtn.disabled = on;
  if (demoBtn) demoBtn.disabled = on;
}

async function doCheck(bookingId) {
  const resultEl = document.getElementById(`result-${bookingId}`);
  resultEl.innerHTML = "";
  _setCardLoading(bookingId, true, "Checking current price...");

  try {
    const res = await fetch(`${API_BASE}/watch/check/${bookingId}`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    if (data.action === "hold") {
      renderHold(data, resultEl);
    } else {
      renderRecommendation(data, resultEl, bookingId);
    }
  } catch (err) {
    resultEl.innerHTML = `<p class="error-banner error-banner--visible">${escapeHtml(err.message)}</p>`;
  } finally {
    _setCardLoading(bookingId, false);
  }
}

async function doDemoDropThenCheck(bookingId) {
  const resultEl = document.getElementById(`result-${bookingId}`);
  resultEl.innerHTML = "";
  _setCardLoading(bookingId, true, "Simulating drop and re-checking...");

  try {
    const dropRes = await fetch(`${API_BASE}/watch/demo-drop/${bookingId}`, { method: "POST" });
    if (!dropRes.ok) {
      const err = await dropRes.json().catch(() => ({}));
      throw new Error(err.detail || `Demo drop failed (HTTP ${dropRes.status})`);
    }
    const checkRes = await fetch(`${API_BASE}/watch/check/${bookingId}`, { method: "POST" });
    const data = await checkRes.json();
    if (!checkRes.ok) throw new Error(data.detail || `HTTP ${checkRes.status}`);
    if (data.action === "hold") {
      renderHold(data, resultEl);
    } else {
      renderRecommendation(data, resultEl, bookingId);
    }
  } catch (err) {
    resultEl.innerHTML = `<p class="error-banner error-banner--visible">${escapeHtml(err.message)}</p>`;
  } finally {
    _setCardLoading(bookingId, false);
  }
}

function renderHold(_data, container) {
  container.innerHTML = `
    <div class="hold-card" style="background:#f8f9fa;border-radius:8px;padding:16px;margin-top:12px;">
      <div style="display:flex;justify-content:flex-end;">
        <button type="button" onclick="this.closest('.hold-card').remove()"
                aria-label="Dismiss"
                style="background:none;border:none;font-size:16px;cursor:pointer;color:var(--color-text-secondary);padding:0 4px;">&#10005;</button>
      </div>
      <div style="font-size:11px;font-weight:600;color:var(--color-text-secondary);letter-spacing:0.05em;margin-bottom:8px;">NO ACTION NEEDED</div>
      <div style="font-size:14px;color:var(--color-text);">No meaningful price drop detected. Check back later or simulate another drop.</div>
    </div>
  `;
}

function renderRecommendation(rec, container, bookingId) {
  const savings = rec.estimated_net_benefit_usd;
  const confidence = rec.confidence;
  const recLabel = rec.recommendation.replace(/_/g, " ");
  const copyBtnId = `copy-email-btn-${bookingId}`;

  container.innerHTML = `
    <div class="card reprice-card" style="margin-top:var(--space-2);">
      <div style="display:flex;justify-content:flex-end;margin-bottom:8px;">
        <button class="watch-result-dismiss" type="button"
                onclick="this.closest('.reprice-card').remove()"
                style="background:none;border:none;font-size:16px;cursor:pointer;color:var(--color-text-secondary);padding:0 4px;"
                aria-label="Dismiss">&#10005;</button>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:var(--space-1);">
        <div>
          <div style="font-size:0.875rem;color:var(--color-text-secondary);text-transform:uppercase;letter-spacing:0.04em;">Estimated savings</div>
          <div style="font-family:var(--font-heading);font-size:2rem;font-weight:500;color:var(--color-accent);">
            $${formatNumber(savings)}
          </div>
        </div>
        <div style="text-align:right;">
          <span class="status-badge status-badge--active">${escapeHtml(confidence)} confidence</span>
          <div style="margin-top:6px;font-size:0.875rem;color:var(--color-text-secondary);text-transform:capitalize;">
            Recommendation: ${escapeHtml(recLabel)}
          </div>
        </div>
      </div>

      <div class="match-card__meta" style="margin-top:var(--space-2);">
        <span class="match-card__meta-item">Was: <span class="match-card__price">$${formatNumber(rec.original_price_usd)}</span></span>
        <span class="match-card__meta-item">Now: <span class="match-card__price">$${formatNumber(rec.new_price_usd)}</span></span>
        <span class="match-card__meta-item">Price delta: $${formatNumber(rec.price_delta_usd)}</span>
      </div>

      <p style="margin:var(--space-2) 0;color:var(--color-text-secondary);font-size:0.875rem;">
        ${escapeHtml(rec.perk_delta_description)}
      </p>

      <p class="match-card__reasoning">${escapeHtml(rec.reasoning)}</p>

      <div style="margin-top:var(--space-3);">
        <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:var(--space-1);">
          <span class="cols-2__heading" style="margin:0;">Email to your travel agent</span>
          <button id="${copyBtnId}" class="btn btn--text" type="button">Copy</button>
        </div>
        <div style="font-size:0.875rem;color:var(--color-text-secondary);margin-bottom:6px;">
          Subject: <span style="color:var(--color-text);">${escapeHtml(rec.suggested_email_subject)}</span>
        </div>
        <pre style="background:var(--color-surface);border:1px solid var(--color-border);
                    border-radius:var(--radius-sm);padding:var(--space-2);
                    font-family:var(--font-mono);font-size:0.8125rem;
                    white-space:pre-wrap;word-wrap:break-word;color:var(--color-text);
                    max-height:320px;overflow-y:auto;">${escapeHtml(rec.suggested_email_body)}</pre>
      </div>
    </div>
  `;

  const copyBtn = document.getElementById(copyBtnId);
  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(rec.suggested_email_body);
        copyBtn.textContent = "Copied";
        setTimeout(() => (copyBtn.textContent = "Copy"), 2000);
      } catch {
        copyBtn.textContent = "Press Cmd+C";
      }
    });
  }
}

/* ----------------------------------------------------------------------
   Helpers
   ---------------------------------------------------------------------- */

function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric", month: "short", day: "numeric",
    });
  } catch {
    return iso;
  }
}

function formatDateTime(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function formatNumber(n) {
  return Number(n).toLocaleString();
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

document.addEventListener("DOMContentLoaded", init);
