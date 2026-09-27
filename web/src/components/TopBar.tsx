"use client";

import { useSession } from "../hooks/useSession";
import { ThemeToggle } from "./ThemeToggle";
import { Wordmark } from "./Wordmark";

export function TopBar() {
  const { authenticated, user, login, logout } = useSession();

  return (
    <div className="topbar">
      <div className="container topbar__inner">
        <div className="topbar__left">
          <Wordmark />
        </div>
        <div className="topbar__right">
          {authenticated ? (
            <button type="button" className="wallet-button" onClick={() => void logout()}>
              <span className="wallet-button__dot" />
              {user ? `${user.wallet.slice(0, 6)}…${user.wallet.slice(-4)}` : "Connected"}
            </button>
          ) : (
            <button type="button" className="pill-button pill-button--sm pill-button--accent" onClick={() => login()}>
              Sign in
            </button>
          )}
          <ThemeToggle />
        </div>
      </div>
    </div>
  );
}
