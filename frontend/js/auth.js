import { initializeApp } from "https://www.gstatic.com/firebasejs/10.11.0/firebase-app.js";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut,
  onAuthStateChanged,
} from "https://www.gstatic.com/firebasejs/10.11.0/firebase-auth.js";

// firebase-api-key: safe to commit — Firebase web API keys are public identifiers
// Access is restricted via Firebase Auth authorized domains, not key secrecy
// See: https://firebase.google.com/docs/projects/api-keys
const firebaseConfig = {
  apiKey: "AIzaSyDHvyi7gfQvbpuEi9vDK1SN8xi-dNgoHU0",  // ok-to-expose
  authDomain: "ms7285-ieor4576-proj03.firebaseapp.com",
  projectId: "ms7285-ieor4576-proj03",
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const provider = new GoogleAuthProvider();

// Guest UUID — persisted in localStorage so an anonymous browser session has a
// stable id we can attach to intakes/watches before the user signs in.
function getGuestId() {
  let id = localStorage.getItem("cruisewise_guest_id");
  if (!id) {
    id = "guest-" + crypto.randomUUID();
    localStorage.setItem("cruisewise_guest_id", id);
  }
  return id;
}

// Returns the current user_id — real Firebase UID if signed in, guest UUID if not.
function getCurrentUserId() {
  const user = auth.currentUser;
  return user ? user.uid : getGuestId();
}

// Returns a flat auth-state object usable from any UI module.
function getAuthState() {
  const user = auth.currentUser;
  if (user) {
    return {
      signed_in: true,
      uid: user.uid,
      email: user.email,
      display_name: user.displayName,
      photo_url: user.photoURL,
    };
  }
  return {
    signed_in: false,
    uid: getGuestId(),
    email: "guestuser@domain.com",
    display_name: "Guest",
    photo_url: null,
  };
}

async function signInWithGoogle() {
  try {
    // Capture the guest id BEFORE the popup so we can hand it to the backend
    // as part of the merge step, even though Firebase will populate
    // auth.currentUser by the time we reach the merge call.
    const guestId = getGuestId();
    const result = await signInWithPopup(auth, provider);
    const user = result.user;

    // Merge guest activity (intakes/watches) into the freshly signed-in user.
    // Non-fatal: the endpoint may not exist yet (router work pending);
    // sign-in itself must still succeed.
    try {
      const token = await user.getIdToken();
      await fetch("/api/account/merge-guest", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ guest_id: guestId }),
      });
    } catch (mergeErr) {
      console.warn("Guest merge skipped:", mergeErr);
    }

    return user;
  } catch (e) {
    console.error("Sign-in failed:", e);
    return null;
  }
}

async function signOutUser() {
  await signOut(auth);
}

// Returns the value to send in the Authorization header on every API call.
// Real Firebase users → `Bearer <id_token>`; guests → `Guest <uuid>`.
async function getAuthHeader() {
  const user = auth.currentUser;
  if (user) {
    const token = await user.getIdToken();
    return `Bearer ${token}`;
  }
  return `Guest ${getGuestId()}`;
}

export {
  auth,
  onAuthStateChanged,
  getCurrentUserId,
  getAuthState,
  getGuestId,
  signInWithGoogle,
  signOutUser,
  getAuthHeader,
};
