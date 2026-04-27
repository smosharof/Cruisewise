// Admin page — not linked from navbar, accessed directly at /admin.html.
// Lists every active watch across users and lets the operator trigger a
// price drop. Demo-only: there is no auth on /api/admin/*.

async function loadAllWatches() {
  try {
    const res = await fetch("/api/admin/watches");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    document.getElementById("admin-error").textContent =
      `Failed to load watches: ${e.message}`;
    document.getElementById("admin-error").style.display = "block";
    return [];
  }
}

function renderWatches(watches) {
  const container = document.getElementById("watches-list");

  if (!watches.length) {
    container.innerHTML =
      '<p style="color:var(--color-text-secondary);">No active watches found.</p>';
    return;
  }

  container.innerHTML = watches
    .map(
      (w) => `
        <div class="watch-card" id="admin-card-${w.booking_id}" style="margin-bottom:16px">
            <div class="watch-card__header">
                <div>
                    <div class="watch-card__ship">${w.ship_name}</div>
                    <div class="watch-card__meta">
                        ${w.cruise_line} · ${w.departure_date} · ${w.cabin_category} ·
                        <span style="color:var(--color-text-secondary);font-size:12px">user: ${w.user_email || w.user_id?.slice(0, 12) || "guest"}</span>
                    </div>
                </div>
            </div>
            <div class="watch-card__prices" style="margin:8px 0">
                <span>Paid: <strong>$${w.price_paid_usd?.toLocaleString()}</strong></span>
                <span>Current: <strong>${w.latest_price ? "$" + w.latest_price.toLocaleString() : "—"}</strong></span>
            </div>
            <div class="watch-card__actions">
                <div style="display:flex;align-items:center;gap:8px;">
                    <label style="font-size:13px;color:var(--color-text-secondary);">Drop amount: $</label>
                    <input type="number" id="drop-${w.booking_id}" value="300" min="50" max="700"
                           style="width:80px;padding:6px 10px;border:1.5px solid var(--color-border);border-radius:6px;font-size:13px"/>
                </div>
                <button class="btn btn--primary btn--sm" onclick="triggerDrop('${w.booking_id}')">
                    Trigger price drop
                </button>
                <span id="result-${w.booking_id}" style="font-size:13px;color:#34a853;display:none">✓ Drop triggered</span>
            </div>
        </div>
    `,
    )
    .join("");
}

async function triggerDrop(bookingId) {
  const dropAmount =
    parseInt(document.getElementById(`drop-${bookingId}`).value) || 300;
  const btn = document.querySelector(`#admin-card-${bookingId} .btn--primary`);
  const resultEl = document.getElementById(`result-${bookingId}`);

  btn.disabled = true;
  btn.textContent = "Triggering...";
  resultEl.style.display = "none";

  try {
    const res = await fetch(`/api/admin/trigger-drop/${bookingId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ drop_amount_usd: dropAmount }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    resultEl.textContent = `✓ $${dropAmount} drop triggered. User will see reprice recommendation on their Watch page.`;
    resultEl.style.display = "inline";
    btn.textContent = "Trigger again";
    btn.disabled = false;

    // Reload to show updated price
    setTimeout(() => init(), 2000);
  } catch (e) {
    btn.textContent = "Trigger price drop";
    btn.disabled = false;
    resultEl.textContent = `✗ Failed: ${e.message}`;
    resultEl.style.color = "#d93025";
    resultEl.style.display = "inline";
  }
}

// Make triggerDrop available globally for onclick handlers
window.triggerDrop = triggerDrop;

async function init() {
  const watches = await loadAllWatches();
  renderWatches(watches);
}

init();
