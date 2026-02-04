import { Outlet, Link, NavLink } from "react-router-dom";
import { UserButton } from "@clerk/clerk-react";

export function Layout() {
  return (
    <div className="flex h-screen flex-col">
      {/* Topbar */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-gray-200 bg-white px-4">
        <div className="flex items-center gap-6">
          <Link to="/" className="flex items-center gap-2 text-lg font-semibold text-gray-900">
            GSD
          </Link>
          <nav className="flex items-center gap-4">
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                `text-sm font-medium ${isActive ? "text-gsd-600" : "text-gray-600 hover:text-gray-900"}`
              }
            >
              Sessions
            </NavLink>
            <NavLink
              to="/tokens"
              className={({ isActive }) =>
                `text-sm font-medium ${isActive ? "text-gsd-600" : "text-gray-600 hover:text-gray-900"}`
              }
            >
              API Tokens
            </NavLink>
          </nav>
        </div>
        <UserButton afterSignOutUrl="/" />
      </header>

      {/* Content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
