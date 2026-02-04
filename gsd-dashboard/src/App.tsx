import { Routes, Route } from "react-router-dom";
import { SignedIn, SignedOut, SignInButton } from "@clerk/clerk-react";
import { Layout } from "./components/Layout";
import { SessionsPage } from "./pages/SessionsPage";
import { LiveSessionPage } from "./pages/LiveSessionPage";

function AuthGate({ children }: { children: React.ReactNode }) {
  return (
    <>
      <SignedOut>
        <div className="min-h-screen flex items-center justify-center bg-gray-50">
          <div className="text-center">
            <h1 className="text-2xl font-bold text-gray-900 mb-4">
              GSD Browser Dashboard
            </h1>
            <p className="text-gray-600 mb-6">Sign in to view sessions</p>
            <SignInButton mode="modal">
              <button className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
                Sign In
              </button>
            </SignInButton>
          </div>
        </div>
      </SignedOut>
      <SignedIn>{children}</SignedIn>
    </>
  );
}

export function App() {
  return (
    <AuthGate>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<SessionsPage />} />
          <Route path="sessions/:id" element={<LiveSessionPage />} />
        </Route>
      </Routes>
    </AuthGate>
  );
}
