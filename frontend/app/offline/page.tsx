import { WifiOffIcon } from "@/components/icons";

export const metadata = { title: "Offline — UniACMIS" };

/**
 * Shown when a page is requested that has never been cached. Its job is to say
 * plainly what is and is not still possible, because "something went wrong" tells
 * a clerk mid-shift nothing useful.
 */
export default function OfflinePage() {
  return (
    <main className="splash">
      <div className="splash__card">
        <span className="splash__brand">
          <WifiOffIcon size={24} />
        </span>
        <h1 className="login__title">No connection</h1>
        <p className="login__sub">This page has not been saved for offline use yet.</p>

        <div className="alert alert--warning" style={{ textAlign: "left" }}>
          <WifiOffIcon size={18} />
          <span>
            Anything you have already entered is safe. Queued entries stay on this
            device and are sent automatically when the connection returns — you do
            not need to retype them.
          </span>
        </div>

        <p className="text-sm muted" style={{ margin: 0 }}>
          Pages you have already opened will still load. Try again once you have a
          signal.
        </p>
      </div>
    </main>
  );
}
