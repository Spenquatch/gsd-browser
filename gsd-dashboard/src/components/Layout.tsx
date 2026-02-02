import { Outlet, Link } from "react-router-dom";

export function Layout() {
  return (
    <div className="flex h-screen flex-col">
      {/* Topbar */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-gray-200 bg-white px-4">
        <Link to="/" className="flex items-center gap-2 text-lg font-semibold text-gray-900">
          GSD
        </Link>
        <div id="clerk-user-button" />
      </header>

      {/* Content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
