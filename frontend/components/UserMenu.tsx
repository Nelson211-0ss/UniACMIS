"use client";

import { useEffect, useRef, useState } from "react";

import { ChevronDownIcon, LogOutIcon } from "@/components/icons";
import type { Me } from "@/lib/api";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function UserMenu({
  user,
  onSignOut,
  align = "down",
  photoUrl,
}: {
  user: Me;
  onSignOut: () => void;
  /** "up" opens the panel above the trigger — for a footer-anchored menu
   * (the sidebar), where "down" would run off the bottom of the viewport. */
  align?: "up" | "down";
  /** A student's registry photo, when there is one — shown square, not in
   * the round initials circle, the same way an ID card holds a photo
   * rather than cropping it into a coin. Falls back to initials on error
   * or when there is none (staff have no registry photo at all). */
  photoUrl?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [photoFailed, setPhotoFailed] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    function onDocClick(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const primaryRole = user.roles[0] ?? "no role";

  return (
    <div className={`menu ${align === "up" ? "menu--up" : ""}`} ref={ref}>
      <button
        type="button"
        className="menu__trigger"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        {photoUrl && !photoFailed ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={photoUrl}
            alt=""
            className="avatar avatar--sm avatar--square"
            onError={() => setPhotoFailed(true)}
          />
        ) : (
          <span className="avatar avatar--sm">{initials(user.full_name)}</span>
        )}
        <span className="menu__name">
          <strong>{user.full_name}</strong>
          <span>{primaryRole.replace(/_/g, " ")}</span>
        </span>
        <ChevronDownIcon size={16} />
      </button>

      {open ? (
        <div className="menu__panel" role="menu">
          <button
            type="button"
            className="menu__item menu__item--danger"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onSignOut();
            }}
          >
            <LogOutIcon size={16} />
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}
