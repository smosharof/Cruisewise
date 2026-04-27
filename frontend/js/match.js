/**
 * match.js — Match page UI logic.
 *
 * Submits the intake synchronously to /api/match/intake, which now blocks
 * until the orchestrator completes (~15-25s). No polling.
 */

import { submitIntake } from "./api.js";
import { getAuthHeader } from "./auth.js";

/* -------------------------------------------------------------------------
   Stopwatch — runs from form submit until results render
   ------------------------------------------------------------------------- */

function makeStopwatch(elId) {
  const el = document.getElementById(elId);
  let timer = null;
  let t0 = 0;
  return {
    start() {
      if (timer) clearInterval(timer);
      t0 = Date.now();
      el.textContent = "0.0s";
      el.style.display = "";
      timer = setInterval(() => {
        el.textContent = ((Date.now() - t0) / 1000).toFixed(1) + "s";
      }, 100);
    },
    stop() {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    },
    reset() {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
      el.textContent = "";
      el.style.display = "none";
    },
  };
}

const _swMatch = makeStopwatch("stopwatch-time");

// Travel-party values where the count is fixed and the field stays hidden.
const HIDDEN_PARTY_SIZE = {
  solo: 1,
  couple: 2,
};

// Travel-party values that reveal the party-size input for free entry.
const SHOW_PARTY_SIZE = ["family_with_kids", "multigen", "friends"];

// Trip-length schema bounds — used when the user picks "Any length".
const DURATION_MIN_DEFAULT = 2;
const DURATION_MAX_DEFAULT = 30;

// Trip-length chip values → schema min/max night ranges.
const TRIP_LENGTH_MAP = {
  any: { min: DURATION_MIN_DEFAULT, max: DURATION_MAX_DEFAULT },
  short: { min: 3, max: 5 },
  week: { min: 6, max: 8 },
  extended: { min: 9, max: 14 },
};

const TRIP_LENGTH_LABELS = {
  any: "Any length",
  short: "Short (3–5 nights)",
  week: "Week (6–8 nights)",
  extended: "Extended (9–14 nights)",
};

// Region values rendered as chips, in the order they appear in the DOM
// (excluding "any"). Used to expand "Any" into the full set on submit.
const ALL_REGIONS = [
  "Alaska",
  "Asia",
  "Australia",
  "Bahamas",
  "Bermuda",
  "Caribbean",
  "Hawaii",
  "Mediterranean",
  "Mexico",
  "Northern Europe",
  "Pacific Coast",
];

// Cruise lines available across the seeded inventory. Order matches what
// the DB stores so an "all selected" intake maps cleanly to "no preference".
const CRUISE_LINES = [
  "Carnival",
  "Celebrity",
  "Disney Cruise Line",
  "Holland America",
  "MSC",
  "Norwegian",
  "Princess",
  "Royal Caribbean",
];

// Departure ports — labels are user-facing; tokens are comma-separated
// substrings the backend's port filter ILIKE-matches against the live DB
// values. Order is the order the dropdown options render in.
const PORTS = [
  { label: "Miami, FL",                    tokens: "Miami,MIA" },
  { label: "Fort Lauderdale, FL",          tokens: "Fort Lauderdale,FLL" },
  { label: "Port Canaveral (Orlando), FL", tokens: "Port Canaveral,PCV,Orlando" },
  { label: "Tampa, FL",                    tokens: "Tampa,TPA" },
  { label: "Galveston, TX",                tokens: "Galveston,GAL" },
  { label: "New York / Cape Liberty, NJ",  tokens: "New York,Cape Liberty,NYC" },
  { label: "Boston, MA",                   tokens: "Boston,BOS" },
  { label: "Philadelphia, PA",             tokens: "Philadelphia,PHL" },
  { label: "Jacksonville, FL",             tokens: "Jacksonville,JAX" },
  { label: "Los Angeles, CA",              tokens: "Los Angeles,Long Beach,LAX" },
  { label: "San Diego, CA",                tokens: "San Diego,SAN" },
  { label: "San Francisco, CA",            tokens: "San Francisco,SFO" },
  { label: "Seattle, WA",                  tokens: "Seattle,SEA" },
  { label: "Vancouver, Canada",            tokens: "Vancouver,YVR,VAN" },
  { label: "Honolulu, HI",                 tokens: "Honolulu,HNL,Hawaii" },
  { label: "Seward / Anchorage, AK",       tokens: "Seward,Anchorage,ANC,Whittier,Fairbanks" },
  { label: "Barcelona, Spain",             tokens: "Barcelona,BCN" },
  { label: "Rome (Civitavecchia), Italy",  tokens: "Civitavecchia,Rome,ROM,CIV" },
  { label: "Athens (Piraeus), Greece",     tokens: "Athens,Piraeus,ATH" },
  { label: "Southampton, UK",              tokens: "Southampton,SOU" },
  { label: "Singapore",                    tokens: "Singapore,SIN" },
  { label: "Tokyo, Japan",                 tokens: "Tokyo,YOK" },
  { label: "Sydney, Australia",            tokens: "Sydney,SYD" },
  { label: "Copenhagen, Denmark",          tokens: "Copenhagen,CPH" },
  { label: "Lisbon, Portugal",             tokens: "Lisbon,LIS" },
  { label: "San Juan, Puerto Rico",        tokens: "San Juan" },
];

// Region → port-label preselection map. When regions change the dropdown
// updates its checked set to the union of these labels.
const REGION_PORT_MAP = {
  "Caribbean":       ["Miami, FL", "Fort Lauderdale, FL", "Port Canaveral (Orlando), FL", "Tampa, FL", "Galveston, TX", "San Juan, Puerto Rico"],
  "Alaska":          ["Seattle, WA", "Vancouver, Canada", "Seward / Anchorage, AK"],
  "Mediterranean":   ["Barcelona, Spain", "Rome (Civitavecchia), Italy", "Athens (Piraeus), Greece"],
  "Northern Europe": ["Southampton, UK", "Copenhagen, Denmark"],
  "Bahamas":         ["Miami, FL", "Fort Lauderdale, FL", "Port Canaveral (Orlando), FL"],
  "Bermuda":         ["New York / Cape Liberty, NJ"],
  "Hawaii":          ["Honolulu, HI", "Los Angeles, CA", "San Francisco, CA"],
  "Mexico":          ["Los Angeles, CA", "San Diego, CA", "Galveston, TX"],
  "Asia":            ["Singapore", "Tokyo, Japan"],
  "Pacific Coast":   ["Los Angeles, CA", "San Francisco, CA", "Seattle, WA", "Vancouver, Canada"],
  "Australia":       ["Sydney, Australia"],
};

function init() {
  const form = document.getElementById("match-form");
  if (!form) return;

  form.addEventListener("submit", handleSubmit);
  bindAllChipGroups();
  bindRestart();
  setDefaultDepartureWindow();
  buildPortDropdown();
  bindPortDropdown();
  buildCruiseLineDropdown();
  bindCruiseLineDropdown();
  bindAdvisoryWatchers();
  setDefaultTripLength();
  setDefaults();
}

function selectChip(groupId, value) {
  // Programmatically click a chip so the group's bound side-effects
  // (party-size visibility, port preselection, error-clearing, advisory
  // refresh) all fire just as if the user had clicked.
  const group = document.getElementById(groupId);
  if (!group) return;
  const chip = group.querySelector(`[data-value="${value}"]`);
  if (chip) chip.click();
}

function setDefaults() {
  // Pre-select the most common answer in every required group so the form
  // is submittable on first paint. The user can override any of these.
  selectChip("travel-party-chips", "couple");
  selectChip("experience-chips", "first_timer");
  selectChip("budget-chips", "2000");
  selectChip("vibe-chips", "relaxation");
  // Region "Any" will deselect every other region and trigger the port
  // dropdown to select all 26 ports via onRegionChange.
  selectChip("region-chips", "any");
}

function setDefaultTripLength() {
  // Pre-select "Any length" so the chip group is never in an empty state.
  const groupEl = document.getElementById("trip-length-chips");
  if (!groupEl) return;
  const anyChip = groupEl.querySelector('.chip[data-value="any"]');
  if (anyChip) anyChip.classList.add("selected");
}

function setDefaultDepartureWindow() {
  // Default to the broadest sensible window so the user never accidentally
  // searches a narrow range that misses available sailings: today through
  // 18 months from now.
  const today = new Date();
  const eighteenMonths = new Date();
  eighteenMonths.setMonth(eighteenMonths.getMonth() + 18);
  const earliestEl = document.getElementById("earliest_departure");
  const latestEl = document.getElementById("latest_departure");
  if (earliestEl) earliestEl.value = today.toISOString().split("T")[0];
  if (latestEl) latestEl.value = eighteenMonths.toISOString().split("T")[0];
}

/* -------------------------------------------------------------------------
   Chip groups
   ------------------------------------------------------------------------- */

function initChipGroup(groupEl, onChange) {
  if (!groupEl) return;
  const chips = groupEl.querySelectorAll(".chip");
  const multi = groupEl.classList.contains("chip-group--multi");

  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      if (multi) {
        chip.classList.toggle("selected");
      } else {
        chips.forEach((c) => c.classList.remove("selected"));
        chip.classList.add("selected");
      }
      if (typeof onChange === "function") {
        onChange(getChipValues(groupEl));
      }
    });
  });
}

function getChipValues(groupEl) {
  if (!groupEl) return [];
  return [...groupEl.querySelectorAll(".chip.selected")].map((c) => c.dataset.value);
}

function getSingleChipValue(groupEl) {
  const values = getChipValues(groupEl);
  return values.length > 0 ? values[0] : null;
}

function bindAllChipGroups() {
  // Three chip groups carry custom side-effects: travel-party drives the
  // party-size field; region drives the port dropdown and its own "Any"
  // toggle; vibe drives a soft advisory. The rest get the generic handler.
  const travelPartyGroup = document.getElementById("travel-party-chips");
  initChipGroup(travelPartyGroup, (values) => {
    onTravelPartyChange(values[0] || null);
    updateAdvisories();
    clearFieldError("error-travel-party");
  });

  bindRegionChipsCustom();

  const vibeGroup = document.getElementById("vibe-chips");
  initChipGroup(vibeGroup, () => {
    updateAdvisories();
    clearFieldError("error-vibe");
  });

  // Budget changes don't have their own chip side-effect but should refresh
  // the advisories (luxury+low-budget warning, plus extended+low-budget).
  const budgetGroup = document.getElementById("budget-chips");
  initChipGroup(budgetGroup, () => {
    updateAdvisories();
    clearFieldError("error-budget");
  });

  // Trip-length chip drives the trip-length advisory.
  const tripLengthGroup = document.getElementById("trip-length-chips");
  initChipGroup(tripLengthGroup, () => updateAdvisories());

  // Cruise experience clears its own validation error on change.
  const experienceGroup = document.getElementById("experience-chips");
  initChipGroup(experienceGroup, () => clearFieldError("error-experience"));

  // Generic single-select binding for any remaining chip groups.
  document
    .querySelectorAll(
      ".chip-group:not(#travel-party-chips):not(#vibe-chips):not(#budget-chips):not(#region-chips):not(#trip-length-chips):not(#experience-chips)",
    )
    .forEach((g) => initChipGroup(g));
}

/* -------------------------------------------------------------------------
   Region chips — "Any" deselects everything else; selecting any other chip
   deselects "Any". Also drives the port dropdown's preselection.
   ------------------------------------------------------------------------- */

function bindRegionChipsCustom() {
  const groupEl = document.getElementById("region-chips");
  if (!groupEl) return;
  const chips = groupEl.querySelectorAll(".chip");

  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const value = chip.dataset.value;
      if (value === "any") {
        // "Any" toggles itself; selecting it deselects every other region.
        const willSelect = !chip.classList.contains("selected");
        chips.forEach((c) => c.classList.remove("selected"));
        if (willSelect) chip.classList.add("selected");
      } else {
        chip.classList.toggle("selected");
        // Selecting any concrete region deselects "Any".
        const anyChip = groupEl.querySelector('.chip[data-value="any"]');
        if (anyChip) anyChip.classList.remove("selected");
      }
      onRegionChange();
      clearFieldError("error-regions");
    });
  });
}

function getSelectedRegions() {
  // Returns the canonical region-name list as it would be sent to the API.
  // "Any" expands to all real regions; otherwise the user's actual selection.
  const groupEl = document.getElementById("region-chips");
  const raw = getChipValues(groupEl);
  if (raw.includes("any")) return [...ALL_REGIONS];
  return raw;
}

function onRegionChange() {
  // Update the port dropdown's checked set based on the new region selection.
  const groupEl = document.getElementById("region-chips");
  const raw = getChipValues(groupEl);

  let labels;
  if (raw.length === 0 || raw.includes("any")) {
    // No regions chosen, or "Any" — select all ports.
    labels = PORTS.map((p) => p.label);
  } else {
    const set = new Set();
    for (const r of raw) {
      const ports = REGION_PORT_MAP[r] || [];
      ports.forEach((p) => set.add(p));
    }
    labels = [...set];
  }
  setPortSelection(labels);
  updateAdvisories();
}

/* -------------------------------------------------------------------------
   Port dropdown — custom multi-select with "select all" / "clear all" controls
   ------------------------------------------------------------------------- */

function buildPortDropdown() {
  const container = document.getElementById("port-dropdown-options");
  if (!container) return;
  // Default state: all ports checked.
  container.innerHTML = PORTS.map(
    (p) => `
      <label class="port-dropdown__option">
        <input type="checkbox" data-label="${escapeAttr(p.label)}"
               data-tokens="${escapeAttr(p.tokens)}" checked />
        <span>${escapeHtml(p.label)}</span>
      </label>`,
  ).join("");
  updatePortDropdownLabel();
}

function bindPortDropdown() {
  const trigger = document.getElementById("port-dropdown-trigger");
  const panel = document.getElementById("port-dropdown-panel");
  const selectAllBtn = document.getElementById("port-select-all");
  const clearAllBtn = document.getElementById("port-clear-all");
  const dropdownEl = document.getElementById("port-dropdown");
  const optionsEl = document.getElementById("port-dropdown-options");
  if (!trigger || !panel) return;

  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    const isOpen = panel.style.display !== "none";
    panel.style.display = isOpen ? "none" : "";
    trigger.setAttribute("aria-expanded", String(!isOpen));
  });

  // Click-outside to close.
  document.addEventListener("click", (e) => {
    if (!dropdownEl.contains(e.target)) {
      panel.style.display = "none";
      trigger.setAttribute("aria-expanded", "false");
    }
  });

  selectAllBtn?.addEventListener("click", () => {
    setPortSelection(PORTS.map((p) => p.label));
  });
  clearAllBtn?.addEventListener("click", () => {
    setPortSelection([]);
  });

  // Live label refresh on individual checkbox change.
  optionsEl?.addEventListener("change", updatePortDropdownLabel);
}

function setPortSelection(labels) {
  const optionsEl = document.getElementById("port-dropdown-options");
  if (!optionsEl) return;
  const want = new Set(labels);
  optionsEl.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
    cb.checked = want.has(cb.dataset.label);
  });
  updatePortDropdownLabel();
}

function getSelectedPortTokens() {
  // For each checked port, return the FIRST token (canonical token used by
  // the backend's IATA expansion). The backend then ILIKE-matches it against
  // the live DB values.
  const optionsEl = document.getElementById("port-dropdown-options");
  if (!optionsEl) return [];
  const tokens = [];
  optionsEl
    .querySelectorAll('input[type="checkbox"]:checked')
    .forEach((cb) => {
      const list = (cb.dataset.tokens || "").split(",");
      if (list[0]) tokens.push(list[0].trim());
    });
  return tokens;
}

function updatePortDropdownLabel() {
  const labelEl = document.getElementById("port-dropdown-label");
  const optionsEl = document.getElementById("port-dropdown-options");
  if (!labelEl || !optionsEl) return;
  const total = PORTS.length;
  const checked = optionsEl.querySelectorAll(
    'input[type="checkbox"]:checked',
  ).length;
  if (checked === 0) {
    labelEl.textContent = "No ports selected";
  } else if (checked === total) {
    labelEl.textContent = `All ports (${total})`;
  } else {
    labelEl.textContent = `${checked} ports selected`;
  }
}

/* -------------------------------------------------------------------------
   Cruise line preference dropdown — same pattern as the port dropdown
   ------------------------------------------------------------------------- */

function buildCruiseLineDropdown() {
  const container = document.getElementById("cruise-line-options");
  if (!container) return;
  // Default state: all lines checked → maps to "no preference" at submit.
  container.innerHTML = CRUISE_LINES.map(
    (line) => `
      <label class="port-dropdown__option">
        <input type="checkbox" data-line="${escapeAttr(line)}" checked />
        <span>${escapeHtml(line)}</span>
      </label>`,
  ).join("");
  updateCruiseLineDropdownLabel();
}

function bindCruiseLineDropdown() {
  const trigger = document.getElementById("cruise-line-trigger");
  const panel = document.getElementById("cruise-line-panel");
  const selectAllBtn = document.getElementById("cruise-line-select-all");
  const clearAllBtn = document.getElementById("cruise-line-clear-all");
  const dropdownEl = document.getElementById("cruise-line-dropdown");
  const optionsEl = document.getElementById("cruise-line-options");
  if (!trigger || !panel) return;

  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    const isOpen = panel.style.display !== "none";
    panel.style.display = isOpen ? "none" : "";
    trigger.setAttribute("aria-expanded", String(!isOpen));
  });

  document.addEventListener("click", (e) => {
    if (!dropdownEl.contains(e.target)) {
      panel.style.display = "none";
      trigger.setAttribute("aria-expanded", "false");
    }
  });

  selectAllBtn?.addEventListener("click", () => {
    setCruiseLineSelection(CRUISE_LINES);
  });
  clearAllBtn?.addEventListener("click", () => {
    setCruiseLineSelection([]);
  });

  optionsEl?.addEventListener("change", updateCruiseLineDropdownLabel);
}

function setCruiseLineSelection(lines) {
  const optionsEl = document.getElementById("cruise-line-options");
  if (!optionsEl) return;
  const want = new Set(lines);
  optionsEl.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
    cb.checked = want.has(cb.dataset.line);
  });
  updateCruiseLineDropdownLabel();
}

function getSelectedCruiseLines() {
  const optionsEl = document.getElementById("cruise-line-options");
  if (!optionsEl) return [];
  const lines = [];
  optionsEl
    .querySelectorAll('input[type="checkbox"]:checked')
    .forEach((cb) => lines.push(cb.dataset.line));
  return lines;
}

function updateCruiseLineDropdownLabel() {
  const labelEl = document.getElementById("cruise-line-label");
  const optionsEl = document.getElementById("cruise-line-options");
  if (!labelEl || !optionsEl) return;
  const total = CRUISE_LINES.length;
  const checked = optionsEl.querySelectorAll(
    'input[type="checkbox"]:checked',
  ).length;
  if (checked === 0) {
    labelEl.textContent = "No cruise lines selected";
  } else if (checked === total) {
    labelEl.textContent = `All cruise lines (${total})`;
  } else if (checked === 1) {
    labelEl.textContent = "1 line selected";
  } else {
    labelEl.textContent = `${checked} lines selected`;
  }
}

/* -------------------------------------------------------------------------
   Soft advisories — non-blocking warnings under affected fields
   ------------------------------------------------------------------------- */

function bindAdvisoryWatchers() {
  // No external watchers needed — trip-length is a chip group whose own
  // initChipGroup callback already calls updateAdvisories(). Kept as a
  // hook for any future non-chip inputs that should refresh advisories.
}

function readBudget() {
  const v = getSingleChipValue(document.getElementById("budget-chips"));
  return v ? parseInt(v, 10) : null;
}

function readTravelParty() {
  return getSingleChipValue(document.getElementById("travel-party-chips"));
}

function readVibe() {
  return getSingleChipValue(document.getElementById("vibe-chips"));
}

function readTripLengthValue() {
  return getSingleChipValue(document.getElementById("trip-length-chips"));
}

function getTripLengthValues() {
  const selected = readTripLengthValue();
  return TRIP_LENGTH_MAP[selected] || TRIP_LENGTH_MAP.any;
}

function getTripLengthAdvisory() {
  const trip = readTripLengthValue();
  const budget = readBudget();
  if (trip === "extended" && budget !== null && budget <= 1000) {
    return "Very few sailings over 9 nights are available under $1,500. Consider a shorter trip or a higher budget.";
  }
  return null;
}

function getVibeAdvisory() {
  const vibe = readVibe();
  const budget = readBudget();
  const party = readTravelParty();
  if (vibe === "luxury" && budget !== null && budget <= 2000) {
    return "Very few luxury sailings are available under $2,500. Consider raising your budget for better results.";
  }
  if (
    vibe === "family_fun" &&
    !["family_with_kids", "multigen"].includes(party)
  ) {
    return "Family Fun sailings work best for families with children. Consider Adventure or Relaxation for couples or solo travelers.";
  }
  return null;
}

function showOrHideAdvisory(elId, message) {
  const el = document.getElementById(elId);
  if (!el) return;
  if (message) {
    el.textContent = message;
    el.style.display = "";
  } else {
    el.textContent = "";
    el.style.display = "none";
  }
}

function updateAdvisories() {
  showOrHideAdvisory("trip-length-advisory", getTripLengthAdvisory());
  showOrHideAdvisory("vibe-advisory", getVibeAdvisory());
}

function onTravelPartyChange(value) {
  const wrapper = document.getElementById("party-size-wrapper");
  const input = document.getElementById("party-size");
  if (!wrapper || !input) return;

  if (HIDDEN_PARTY_SIZE[value] !== undefined) {
    input.value = HIDDEN_PARTY_SIZE[value];
    wrapper.style.display = "none";
  } else if (SHOW_PARTY_SIZE.includes(value)) {
    wrapper.style.display = "";
    input.value = "";
    input.focus();
  }
}

function bindRestart() {
  const btn = document.getElementById("match-restart");
  if (!btn) return;
  btn.addEventListener("click", () => {
    _swMatch.reset();
    document.getElementById("match-results-wrapper").style.display = "none";
    document.getElementById("match-form-wrapper").style.display = "";
    document.getElementById("match-results").innerHTML = "";
    const summaryEl = document.getElementById("intake-summary-container");
    if (summaryEl) summaryEl.innerHTML = "";
    const noticeEl = document.getElementById("preference-notice");
    if (noticeEl) noticeEl.innerHTML = "";
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

/* -------------------------------------------------------------------------
   Submit + validation
   ------------------------------------------------------------------------- */

function collectIntake() {
  const travelPartyGroup = document.getElementById("travel-party-chips");
  const vibeGroup = document.getElementById("vibe-chips");
  const experienceGroup = document.getElementById("experience-chips");
  const budgetGroup = document.getElementById("budget-chips");

  const budgetRaw = getSingleChipValue(budgetGroup);

  // Trip length comes from a single-select chip group. Each chip value maps
  // to a (min, max) pair via TRIP_LENGTH_MAP. "Any length" expands to the
  // schema's own bounds so the SQL filter is effectively unconstrained.
  const tripLength = getTripLengthValues();
  const durationMin = tripLength.min;
  const durationMax = tripLength.max;

  return {
    travel_party: getSingleChipValue(travelPartyGroup),
    party_size: parseInt(document.getElementById("party-size").value, 10),
    primary_vibe: getSingleChipValue(vibeGroup),
    secondary_vibes: [],
    budget_per_person_usd: budgetRaw ? parseInt(budgetRaw, 10) : null,
    flexible_dates: document.getElementById("flexible_dates").checked,
    earliest_departure: document.getElementById("earliest_departure").value,
    latest_departure: document.getElementById("latest_departure").value,
    duration_nights_min: durationMin,
    duration_nights_max: durationMax,
    preferred_regions: getSelectedRegions(),
    departure_ports_acceptable: getSelectedPortTokens(),
    must_haves: [],
    deal_breakers: [],
    // "All selected" maps to "no preference" (empty list) so the backend
    // boost is a no-op for users who didn't narrow the dropdown.
    preferred_cruise_lines: (() => {
      const sel = getSelectedCruiseLines();
      return sel.length === CRUISE_LINES.length ? [] : sel;
    })(),
    cruise_experience_level: getSingleChipValue(experienceGroup),
  };
}

function setFieldError(id, message) {
  const el = document.getElementById(id);
  if (el) el.textContent = message;
}

function clearFieldError(id) {
  const el = document.getElementById(id);
  if (el) el.textContent = "";
}

const REQUIRED_ERROR_IDS = [
  "error-travel-party",
  "error-vibe",
  "error-budget",
  "error-regions",
  "error-experience",
];

function validateIntake(intake) {
  let valid = true;

  REQUIRED_ERROR_IDS.forEach(clearFieldError);

  if (!intake.travel_party) {
    setFieldError("error-travel-party", "Please choose who is traveling.");
    valid = false;
  }
  if (!intake.primary_vibe) {
    setFieldError("error-vibe", "Please choose a vibe.");
    valid = false;
  }
  if (!intake.budget_per_person_usd) {
    setFieldError("error-budget", "Please choose a budget.");
    valid = false;
  }
  if (!intake.preferred_regions || intake.preferred_regions.length === 0) {
    setFieldError("error-regions", "Please choose at least one region.");
    valid = false;
  }
  if (!intake.cruise_experience_level) {
    setFieldError(
      "error-experience",
      "Please choose your cruise experience.",
    );
    valid = false;
  }

  if (!valid) {
    // Scroll the first non-empty inline error into view so the user notices.
    const firstError = [...document.querySelectorAll(".field-error")].find(
      (el) => el.textContent.trim().length > 0,
    );
    if (firstError) {
      firstError.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  return valid;
}

async function handleSubmit(e) {
  e.preventDefault();

  const intake = collectIntake();
  if (!validateIntake(intake)) {
    return;
  }
  await runMatchSubmit(intake);
}

/**
 * Reusable submit path: handles loading state, stopwatch, API call, results
 * rendering, and error messaging. Called by the form-submit handler and by
 * the "Show preferred lines only" preference-notice CTA.
 */
async function runMatchSubmit(intake) {
  const submitBtn = document.getElementById("match-submit");
  const loadingEl = document.getElementById("match-loading");

  if (submitBtn) submitBtn.disabled = true;
  if (loadingEl) loadingEl.style.display = "inline-flex";
  _swMatch.start();

  try {
    const result = await submitIntake(intake);
    showResults(result, intake);
  } catch (err) {
    _swMatch.stop();
    let message;
    if (err.status === 422) {
      message =
        "No sailings match these filters. Try widening the dates, regions, or budget.";
    } else if (err.status === 500) {
      message =
        "Something went wrong on our side. Please try again in a moment.";
    } else {
      message = err.message || "Unable to submit your intake.";
    }
    setFieldError("error-regions", message);
    const el = document.getElementById("error-regions");
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
  } finally {
    if (submitBtn) submitBtn.disabled = false;
    if (loadingEl) loadingEl.style.display = "none";
  }
}

/* -------------------------------------------------------------------------
   Results rendering
   ------------------------------------------------------------------------- */

function renderIntakeSummary(intake) {
  const PARTY_LABELS = {
    solo: "Just me",
    couple: "A couple",
    family_with_kids: "Families",
    multigen: "Multi-gen",
    friends: "Friends",
  };
  const VIBE_LABELS = {
    relaxation: "Relaxation",
    adventure: "Adventure",
    party: "Party",
    family_fun: "Family Fun",
    luxury: "Luxury",
    cultural: "Cultural",
  };
  const BUDGET_LABELS = BUDGET_LABEL_MAP;
  const EXPERIENCE_LABELS = {
    first_timer: "First timer",
    occasional: "Been once or twice",
    loyal_cruiser: "Seasoned cruiser",
  };

  // Regions: collapse the full list to "Any Region" when it matches every
  // real region (the "Any Region" chip expands to ALL_REGIONS at submit).
  const regions = intake.preferred_regions || [];
  const isAnyRegion =
    regions.length === ALL_REGIONS.length &&
    ALL_REGIONS.every((r) => regions.includes(r));
  const regionsTag = isAnyRegion ? "Any Region" : regions.join(", ");

  // Departure ports: empty array or all-selected collapses to "All ports".
  // Up to 3 selections render as comma-joined city names (the bit before the
  // comma in each PORT.label); 4+ collapses to "<n> ports" to keep the row tidy.
  const selectedPorts = intake.departure_ports_acceptable || [];
  const isAllPorts =
    selectedPorts.length === 0 || selectedPorts.length >= PORTS.length;
  let portsTag;
  if (isAllPorts) {
    portsTag = "All ports";
  } else if (selectedPorts.length <= 3) {
    const portLabels = selectedPorts.map((token) => {
      const port = PORTS.find((p) => p.tokens.split(",")[0] === token);
      return port ? port.label.split(",")[0] : token;
    });
    portsTag = portLabels.join(", ");
  } else {
    portsTag = `${selectedPorts.length} ports`;
  }

  // Trip length: derive which chip key produced the (min, max) so we can
  // display its human label rather than raw "7–8 nights".
  const tripKey =
    Object.keys(TRIP_LENGTH_MAP).find(
      (k) =>
        TRIP_LENGTH_MAP[k].min === intake.duration_nights_min &&
        TRIP_LENGTH_MAP[k].max === intake.duration_nights_max,
    ) || "any";
  const tripTag = TRIP_LENGTH_LABELS[tripKey];

  const tags = [
    PARTY_LABELS[intake.travel_party],
    VIBE_LABELS[intake.primary_vibe],
    BUDGET_LABELS[intake.budget_per_person_usd],
    tripTag,
    regionsTag,
    portsTag,
    EXPERIENCE_LABELS[intake.cruise_experience_level],
  ].filter(Boolean);

  // Preferred cruise lines: only render the tag when the user narrowed the
  // dropdown — empty list means "no preference" and shouldn't surface here.
  if (
    intake.preferred_cruise_lines &&
    intake.preferred_cruise_lines.length > 0
  ) {
    tags.push(intake.preferred_cruise_lines.join(", "));
  }

  const container = document.getElementById("intake-summary-container");
  if (!container) return;
  container.innerHTML = `
    <div class="intake-summary">
      ${tags.map((t) => `<span class="intake-tag">${escapeHtml(t)}</span>`).join("")}
    </div>`;
}

/**
 * Show a soft notice when the user has preferred cruise lines but none of
 * the returned candidates are from those lines. Includes a CTA that re-runs
 * the search with relaxed filters (any region, any duration, no budget cap)
 * keeping only the preferred lines so the user can see what those lines do
 * have available.
 */
// Map of budget chip values → human label. Shared between the intake summary
// renderer and the relaxed-search CTA so both surfaces show the same string.
const BUDGET_LABEL_MAP = {
  1000: "Under $1,500",
  2000: "$1,500–$2,500",
  3250: "$2,500–$4,000",
  8000: "$4,000+",
};

function renderPreferenceNotice(intake, candidates) {
  const container = document.getElementById("preference-notice");
  if (!container) return;

  // No preferred lines selected → nothing to show.
  if (
    !intake.preferred_cruise_lines ||
    intake.preferred_cruise_lines.length === 0
  ) {
    container.innerHTML = "";
    return;
  }

  // Post-CTA reload: relaxed_search is true and we've already broadened
  // every filter. Render the BLUE info notice that explains why prices may
  // exceed the original budget — the LLM also acknowledges this in
  // fit_reasoning, but we surface it visually too.
  if (intake.relaxed_search && intake.original_budget_label) {
    const preferredLabel = intake.preferred_cruise_lines.join(", ");
    container.innerHTML = `
      <div class="preference-notice preference-notice--info">
        <span class="preference-notice__text">
          No ${escapeHtml(preferredLabel)} sailings matched your ${escapeHtml(intake.original_budget_label)} budget. The options below are the closest matches — prices may be higher than your original budget.
        </span>
      </div>`;
    return;
  }

  const preferredLower = intake.preferred_cruise_lines.map((l) =>
    l.toLowerCase(),
  );
  const anyMatch = candidates.some((c) =>
    preferredLower.includes((c.cruise_line || "").toLowerCase()),
  );
  if (anyMatch) {
    container.innerHTML = "";
    return;
  }

  const preferredLabel = intake.preferred_cruise_lines.join(", ");
  container.innerHTML = `
    <div class="preference-notice">
      <span class="preference-notice__text">
        None of your preferred cruise lines (${escapeHtml(preferredLabel)}) had sailings matching your filters. Showing the best alternatives.
      </span>
      <button class="preference-notice__action" id="show-preferred-only" type="button">
        Show ${escapeHtml(preferredLabel)} sailings only
      </button>
    </div>`;

  document
    .getElementById("show-preferred-only")
    .addEventListener("click", () => {
      // Capture the original budget label BEFORE we overwrite the value, so
      // the backend prompt can reference what the user actually asked for.
      const originalBudgetLabel =
        BUDGET_LABEL_MAP[intake.budget_per_person_usd] || "";

      // Re-run search with preferred lines kept, every other filter relaxed
      // to its broadest setting so the user can see what those lines offer.
      const relaxedIntake = {
        ...intake,
        relaxed_search: true,
        original_budget_label: originalBudgetLabel,
        duration_nights_min: 2,
        duration_nights_max: 30,
        budget_per_person_usd: 50000,
        departure_ports_acceptable: [],
        preferred_regions: [
          "Caribbean",
          "Alaska",
          "Mediterranean",
          "Northern Europe",
          "Bahamas",
          "Bermuda",
          "Hawaii",
          "Mexico",
          "Asia",
          "Pacific Coast",
          "Australia",
        ],
      };
      runMatchSubmit(relaxedIntake);
    });
}

function showResults(result, intake) {
  _swMatch.stop();
  document.getElementById("match-form-wrapper").style.display = "none";
  const wrapper = document.getElementById("match-results-wrapper");
  const container = document.getElementById("match-results");
  if (intake) renderIntakeSummary(intake);
  if (intake) renderPreferenceNotice(intake, result.ranked_candidates || []);

  container.innerHTML = "";
  result.ranked_candidates.forEach((c, i) => {
    container.appendChild(renderCard(c, i));
  });

  // "Watch this price" opens the inline slide-in panel rather than navigating away.
  // We tag the clicked button with data-active="true" so the form submit handler
  // can find it again to flip it to "✓ Watching" after a successful register.
  container.querySelectorAll(".watch-this-price").forEach((btn) => {
    btn.addEventListener("click", () => {
      try {
        const sailing = JSON.parse(btn.dataset.sailing);
        document
          .querySelectorAll('.watch-this-price[data-active="true"]')
          .forEach((b) => (b.dataset.active = "false"));
        btn.dataset.active = "true";
        openWatchPanel(sailing);
      } catch (e) {
        console.warn("watch-this-price: malformed dataset", e);
      }
    });
  });

  if (result.top_pick_reasoning) {
    container.appendChild(
      renderCallout("Why this top pick", result.top_pick_reasoning, "callout--top-pick"),
    );
  }
  if (result.counter_memo) {
    container.appendChild(
      renderCallout("Something to consider", result.counter_memo, "callout--muted"),
    );
  }
  if (result.gaps_identified && result.gaps_identified.length > 0) {
    container.appendChild(renderGaps(result.gaps_identified));
  }

  wrapper.style.display = "";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderCard(c, index) {
  const card = document.createElement("article");
  card.className = "match-card";

  const vibePct = Math.round((c.vibe_score || 0) * 100);
  const cabinLabel = c.cabin_category_priced
    ? c.cabin_category_priced.charAt(0).toUpperCase() +
      c.cabin_category_priced.slice(1)
    : "Cabin";

  const departureDate = formatDate(c.departure_date);

  card.innerHTML = `
    <div class="match-card__header">
      <div>
        <div class="match-card__title">${escapeHtml(c.ship_name)}</div>
        <div class="match-card__line">${escapeHtml(c.cruise_line)}${index === 0 ? " &middot; Top match" : ""}</div>
      </div>
      <div class="match-card__price">${cabinLabel} from ${formatPrice(c.cabin_price_usd, c.currency)}</div>
    </div>

    <div class="match-card__meta">
      <span class="match-card__meta-item">${escapeHtml(departureDate)}</span>
      <span class="match-card__meta-item">${c.duration_nights} nights</span>
      <span class="match-card__meta-item">From ${escapeHtml(c.departure_port)}</span>
    </div>

    <div class="match-card__line" style="margin-bottom:var(--space-1);">
      ${escapeHtml(c.itinerary_summary)}
    </div>

    <div class="vibe-bar">
      <div class="vibe-bar__label">
        <span>Vibe fit</span>
        <span>${vibePct}%</span>
      </div>
      <div class="vibe-bar__track">
        <div class="vibe-bar__fill" style="width:${vibePct}%;"></div>
      </div>
    </div>

    <p class="match-card__reasoning">${escapeHtml(c.fit_reasoning)}</p>

    <div class="cols-2">
      <div>
        <div class="cols-2__heading">Strengths</div>
        <ul>${(c.strengths || []).map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>
      </div>
      <div>
        <div class="cols-2__heading">Concerns</div>
        <ul>${(c.concerns || []).map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>
      </div>
    </div>

    ${
      c.review_sentiment_summary
        ? `<p class="match-card__line" style="margin-top:var(--space-2);font-style:italic;">${escapeHtml(c.review_sentiment_summary)}</p>`
        : ""
    }

    <div class="match-card__cta">
      <a class="btn btn--primary" href="${escapeAttr(c.booking_affiliate_url)}" target="_blank" rel="noopener">View sailing</a>
      <button type="button" class="btn btn--text watch-this-price" data-sailing='${escapeAttr(
        JSON.stringify({
          cruise_line: c.cruise_line,
          ship_name: c.ship_name,
          sailing_id: c.sailing_id,
          departure_date: c.departure_date,
          cabin_category: c.cabin_category_priced,
          starting_price_usd: c.cabin_price_usd,
          currency: c.currency,
          itinerary_summary: c.itinerary_summary,
          departure_port: c.departure_port,
        }),
      )}'>Watch this price</button>
    </div>
  `;
  return card;
}

function renderCallout(label, body, modifier) {
  const el = document.createElement("div");
  el.className = `callout ${modifier}`;
  el.innerHTML = `
    <span class="callout__label">${escapeHtml(label)}</span>
    <p class="callout__body">${escapeHtml(body)}</p>
  `;
  return el;
}

function renderGaps(gaps) {
  const el = document.createElement("div");
  el.className = "gaps";
  el.innerHTML = `
    <div class="gaps__title">Worth verifying before you book</div>
    <ul>${gaps.map((g) => `<li>${escapeHtml(g)}</li>`).join("")}</ul>
  `;
  return el;
}

/* -------------------------------------------------------------------------
   Helpers
   ------------------------------------------------------------------------- */

function formatDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

function formatPrice(amount, currency = "USD") {
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency,
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${currency} ${Number(amount).toLocaleString()}`;
  }
}

function formatNumber(n) {
  return Number(n).toLocaleString();
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[c]);
}

function escapeAttr(s) {
  return escapeHtml(s);
}

document.addEventListener("DOMContentLoaded", init);

/* ----------------------------------------------------------------------
   Watch panel — inline slide-in from a Match card. Replaces the old
   navigation to watch.html so the user keeps their results visible.
   ---------------------------------------------------------------------- */

function openWatchPanel(sailing) {
  document.getElementById("wp-cruise-line").value = sailing.cruise_line || "";
  document.getElementById("wp-ship-name").value = sailing.ship_name || "";
  document.getElementById("wp-departure-date").value = sailing.departure_date || "";
  document.getElementById("wp-cabin-category").value = sailing.cabin_category || "";
  document.getElementById("wp-price-paid").value = sailing.starting_price_usd || "";

  document.getElementById("watch-panel-success").style.display = "none";
  document.getElementById("watch-panel-form").style.display = "";
  document.getElementById("watch-panel-error").textContent = "";
  document.getElementById("wp-final-payment").value = "";
  document.getElementById("wp-perks").value = "";

  const panel = document.getElementById("watch-panel");
  const overlay = document.getElementById("watch-panel-overlay");
  panel.dataset.sailing = JSON.stringify(sailing);

  overlay.style.display = "block";
  panel.removeAttribute("aria-hidden");
  requestAnimationFrame(() => panel.classList.add("open"));

  setTimeout(() => document.getElementById("wp-price-paid").focus(), 260);
}

function closeWatchPanel() {
  const panel = document.getElementById("watch-panel");
  const overlay = document.getElementById("watch-panel-overlay");
  if (!panel || !overlay) return;
  panel.classList.remove("open");
  panel.setAttribute("aria-hidden", "true");
  setTimeout(() => (overlay.style.display = "none"), 250);
}

(function bindWatchPanel() {
  const panel = document.getElementById("watch-panel");
  if (!panel) return;

  document.getElementById("watch-panel-close").addEventListener("click", closeWatchPanel);
  document.getElementById("watch-panel-overlay").addEventListener("click", closeWatchPanel);
  document.getElementById("watch-panel-done").addEventListener("click", closeWatchPanel);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeWatchPanel();
  });

  document.getElementById("watch-panel-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const sailing = JSON.parse(panel.dataset.sailing || "{}");
    const finalPayment = document.getElementById("wp-final-payment").value;
    const pricePaid = parseInt(document.getElementById("wp-price-paid").value, 10);
    const perks = document
      .getElementById("wp-perks")
      .value.split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    const errorEl = document.getElementById("watch-panel-error");
    if (!finalPayment) {
      errorEl.textContent = "Please enter a final payment date.";
      return;
    }
    if (!pricePaid || pricePaid < 100) {
      errorEl.textContent = "Please confirm the price you paid.";
      return;
    }
    errorEl.textContent = "";

    const submitBtn = document.getElementById("watch-panel-submit");
    const loadingEl = document.getElementById("watch-panel-loading");
    submitBtn.disabled = true;
    loadingEl.style.display = "inline";

    const payload = {
      booking_id: crypto.randomUUID(),
      user_id: "00000000-0000-0000-0000-000000000000",
      sailing_id: sailing.sailing_id || `watch-${Date.now()}`,
      cruise_line: sailing.cruise_line,
      ship_name: sailing.ship_name,
      departure_date: sailing.departure_date,
      cabin_category: sailing.cabin_category || "interior",
      price_paid_usd: pricePaid,
      perks_at_booking: perks,
      booking_source: "match",
      final_payment_date: finalPayment,
      created_at: new Date().toISOString(),
    };

    try {
      const authHeader = await getAuthHeader();
      const res = await fetch("/api/watch/register", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: authHeader,
        },
        body: JSON.stringify(payload),
      });
      if (res.status === 409) {
        errorEl.innerHTML =
          'You\'re already watching this sailing. ' +
          '<a href="watch.html" style="color:var(--color-accent);text-decoration:underline;">Visit the Watch page</a> ' +
          'to check its status.';
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      document.getElementById("watch-panel-form").style.display = "none";
      document.getElementById("watch-panel-success").style.display = "block";

      const activeBtn = document.querySelector('.watch-this-price[data-active="true"]');
      if (activeBtn) {
        activeBtn.textContent = "✓ Watching";
        activeBtn.disabled = true;
        activeBtn.style.color = "#34a853";
        activeBtn.dataset.active = "false";
      }
    } catch (err) {
      errorEl.textContent = "Something went wrong. Please try again.";
    } finally {
      submitBtn.disabled = false;
      loadingEl.style.display = "none";
    }
  });
})();
