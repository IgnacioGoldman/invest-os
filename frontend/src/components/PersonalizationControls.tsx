import type { Session } from "@supabase/supabase-js";
import { Bell, CheckCheck, LogIn, LogOut, UserRound, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { StockNotification } from "../personalization";

type Panel = "account" | "notifications" | null;

type Props = {
  configured: boolean;
  session: Session | null;
  notifications: StockNotification[];
  onSignIn: () => Promise<void>;
  onSignOut: () => Promise<void>;
  onReadNotification: (id: string) => Promise<void>;
  onReadAllNotifications: () => Promise<void>;
  onOpenTicker: (ticker: string) => void;
};

function relativeTime(value: string) {
  const seconds = Math.round((Date.parse(value) - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (Math.abs(seconds) < 60) return formatter.format(seconds, "second");
  const minutes = Math.round(seconds / 60);
  if (Math.abs(minutes) < 60) return formatter.format(minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return formatter.format(hours, "hour");
  return formatter.format(Math.round(hours / 24), "day");
}

export function PersonalizationControls({
  configured,
  session,
  notifications,
  onSignIn,
  onSignOut,
  onReadNotification,
  onReadAllNotifications,
  onOpenTicker,
}: Props) {
  const [panel, setPanel] = useState<Panel>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const unreadCount = notifications.filter((item) => !item.read_at).length;
  const avatar = session?.user.user_metadata.avatar_url as string | undefined;
  const name = (session?.user.user_metadata.full_name as string | undefined) ?? session?.user.email ?? "Account";

  useEffect(() => {
    if (!panel) return undefined;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPanel(null);
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [panel]);

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
      <div className="mobile-personal-actions">
        {session && (
          <button
            type="button"
            className="mobile-header-icon"
            onClick={() => setPanel("notifications")}
            aria-label={`${unreadCount} unread notifications`}
            title="Notifications"
          >
            <Bell size={20} />
            {unreadCount > 0 && <span>{Math.min(unreadCount, 99)}</span>}
          </button>
        )}
        <button
          type="button"
          className="mobile-header-icon mobile-account-button"
          onClick={() => setPanel("account")}
          aria-label={session ? "Open account" : "Sign in"}
          title={session ? "Account" : "Sign in"}
        >
          {avatar ? <img src={avatar} alt="" referrerPolicy="no-referrer" /> : <UserRound size={21} />}
        </button>
      </div>

      {panel && (
        <div className="mobile-sheet-backdrop mobile-personal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.currentTarget === event.target) setPanel(null);
        }}>
          <section className="mobile-personal-sheet" role="dialog" aria-modal="true" aria-label={panel === "account" ? "Account" : "Notifications"}>
            <div className="mobile-sheet-handle" aria-hidden="true" />
            <header>
              <div>
                <h2>{panel === "account" ? "Account" : "Notifications"}</h2>
                <p>{panel === "account" ? "Sync your filters across devices." : "New matches from your saved filters."}</p>
              </div>
              <button type="button" className="mobile-icon-button" onClick={() => setPanel(null)} aria-label="Close">
                <X size={20} />
              </button>
            </header>

            {panel === "account" ? (
              <div className="mobile-account-content">
                {session ? (
                  <>
                    <div className="mobile-account-identity">
                      {avatar ? <img src={avatar} alt="" referrerPolicy="no-referrer" /> : <UserRound size={24} />}
                      <div><strong>{name}</strong><span>{session.user.email}</span></div>
                    </div>
                    <p>Your saved filters and alerts are private to this account.</p>
                    <button type="button" className="mobile-secondary-action" disabled={busy} onClick={() => void run(async () => {
                      await onSignOut();
                      setPanel(null);
                    })}>
                      <LogOut size={17} />Sign out
                    </button>
                  </>
                ) : (
                  <>
                    <div className="mobile-signin-mark"><UserRound size={28} /></div>
                    <strong>Make your stock screen yours</strong>
                    <p>Save custom filters, turn on match alerts, and pick up on another device.</p>
                    <button type="button" className="mobile-google-button" disabled={busy} onClick={() => void run(onSignIn)}>
                      <LogIn size={18} />Continue with Google
                    </button>
                  </>
                )}
                {error && <p className="mobile-personal-error">{error}</p>}
              </div>
            ) : (
              <div className="mobile-notification-content">
                {unreadCount > 0 && (
                  <button type="button" className="mobile-read-all" disabled={busy} onClick={() => void run(onReadAllNotifications)}>
                    <CheckCheck size={16} />Mark all read
                  </button>
                )}
                {notifications.length === 0 ? (
                  <div className="mobile-notification-empty">
                    <Bell size={24} />
                    <strong>Nothing new yet</strong>
                    <p>Turn on alerts for a saved filter and new matching symbols will appear here.</p>
                  </div>
                ) : (
                  <div className="mobile-notification-list">
                    {notifications.map((notification) => (
                      <button
                        type="button"
                        key={notification.id}
                        className={notification.read_at ? "" : "unread"}
                        onClick={() => void run(async () => {
                          if (!notification.read_at) await onReadNotification(notification.id);
                          onOpenTicker(notification.ticker);
                          setPanel(null);
                        })}
                      >
                        <span className="mobile-notification-symbol">{notification.ticker}</span>
                        <span><strong>{notification.title}</strong><small>{notification.body}</small></span>
                        <time>{relativeTime(notification.created_at)}</time>
                      </button>
                    ))}
                  </div>
                )}
                {error && <p className="mobile-personal-error">{error}</p>}
              </div>
            )}
          </section>
        </div>
      )}
    </>
  );
}
