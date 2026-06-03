"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const tabs = [
  { href: "/", label: "Overview" },
  { href: "/copilot", label: "Copilot" },
  { href: "/shrink", label: "Shrink" },
  { href: "/lens", label: "Lens" },
  { href: "/trace", label: "Trace" },
];

export default function Nav() {
  const path = usePathname() || "/";
  return (
    <header className="nav">
      <Link href="/" className="brand">
        <span className="brand-mark" aria-hidden>
          <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
            <rect x="1.2" y="1.2" width="19.6" height="19.6" rx="6" stroke="#c8f23f" strokeWidth="1.4" />
            <circle cx="7" cy="7" r="2.1" fill="#c8f23f" />
            <circle cx="15" cy="15" r="2.1" fill="#35d6a4" />
            <path d="M7 9.1v1.6a3 3 0 0 0 3 3h2.8" stroke="#969cb0" strokeWidth="1.3" />
          </svg>
        </span>
        gitly
      </Link>
      <nav className="nav-links">
        {tabs.map((t) => {
          const active = t.href === "/" ? path === "/" : path.startsWith(t.href);
          return (
            <Link key={t.href} href={t.href} className={`nav-link${active ? " active" : ""}`}>
              {t.label}
            </Link>
          );
        })}
      </nav>
      <a className="nav-cta" href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
        API ↗
      </a>
    </header>
  );
}
