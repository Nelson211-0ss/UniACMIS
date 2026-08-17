export const metadata = { title: "Offline — UniACMIS" };

/**
 * Shown when a page is requested that has never been cached. Its job is to say
 * plainly what is and is not still possible, because "something went wrong" tells
 * a clerk mid-shift nothing useful.
 */
export default function OfflinePage() {
  return (
    <main className="login">
      <div className="login__card">
        <h1 className="login__title">No connection</h1>
        <p className="login__sub">
          This page has not been saved for offline use yet.
        </p>

        <div className="alert alert--warning">
          Anything you have already entered is safe. Queued entries stay on this
          device and are sent automatically when the connection returns — you do not
          need to retype them.
        </div>

        <p style={{ fontSize: "0.9375rem", color: "var(--on-surface-variant)" }}>
          Pages you have already opened will still load. Try again once you have a
          signal.
        </p>
      </div>
    </main>
  );
}
