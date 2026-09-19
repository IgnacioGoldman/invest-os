import type { Session } from "@supabase/supabase-js";
import { LogIn, LogOut, UserRound, X } from "lucide-react";
import { useEffect, useState } from "react";

type Props = {
  configured: boolean;
  session: Session | null;
  onSignIn: () => Promise<void>;
  onSignOut: () => Promise<void>;
};

export function PersonalizationControls({ configured, session, onSignIn, onSignOut }: Props) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const avatar = session?.user.user_metadata.avatar_url as string | undefined;
  const name = (session?.user.user_metadata.full_name as string | undefined) ?? session?.user.email ?? "Account";

  useEffect(() => {
    if (!open) return undefined;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [open]);

  if (!configured) return null;

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        type="button"
        className="mobile-header-icon mobile-account-button"
        onClick={() => setOpen(true)}
        aria-label={session ? "Open account" : "Sign in"}
        title={session ? "Account" : "Sign in"}
      >
        {avatar ? <img src={avatar} alt="" referrerPolicy="no-referrer" /> : <UserRound size={21} />}
      </button>

      {open && (
        <div className="mobile-sheet-backdrop mobile-personal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.currentTarget === event.target) setOpen(false);
        }}>
          <section className="mobile-personal-sheet" role="dialog" aria-modal="true" aria-label="Account">
            <div className="mobile-sheet-handle" aria-hidden="true" />
            <header>
              <div><h2>Account</h2><p>Sync your watchlist and filters across devices.</p></div>
              <button type="button" className="mobile-icon-button" onClick={() => setOpen(false)} aria-label="Close">
                <X size={20} />
              </button>
            </header>

            <div className="mobile-account-content">
              {session ? (
                <>
                  <div className="mobile-account-identity">
                    {avatar ? <img src={avatar} alt="" referrerPolicy="no-referrer" /> : <UserRound size={24} />}
                    <div><strong>{name}</strong><span>{session.user.email}</span></div>
                  </div>
                  <p>Your watchlist, custom filters, and daily match badges are private to this account.</p>
                  <button type="button" className="mobile-secondary-action" disabled={busy} onClick={() => void run(async () => {
                    await onSignOut();
                    setOpen(false);
                  })}>
                    <LogOut size={17} />Sign out
                  </button>
                </>
              ) : (
                <>
                  <div className="mobile-signin-mark"><UserRound size={28} /></div>
                  <strong>Make your stock screen yours</strong>
                  <p>Build a watchlist, save custom filters, and see daily new-match badges.</p>
                  <button type="button" className="mobile-google-button" disabled={busy} onClick={() => void run(onSignIn)}>
                    <LogIn size={18} />Continue with Google
                  </button>
                </>
              )}
              {error && <p className="mobile-personal-error">{error}</p>}
            </div>
          </section>
        </div>
      )}
    </>
  );
}
