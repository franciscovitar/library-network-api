"use client";

import { signIn, signOut } from "next-auth/react";

/** Auth.js client helpers use built-in CSRF and provider OAuth endpoints. */
export function SignInButton() {
  return (
    <button type="button" className="button button-primary full-width"
      onClick={() => { void signIn("github", { redirectTo: "/workspace" }); }}>
      Continuar con GitHub <span aria-hidden="true">↗</span>
    </button>
  );
}

export function SignOutButton() {
  return (
    <button type="button" className="signout-button"
      onClick={() => { void signOut({ redirectTo: "/" }); }}>
      Cerrar sesión <span aria-hidden="true">↗</span>
    </button>
  );
}
