import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ClerkProvider } from "@clerk/clerk-react";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import "./index.css";

const clerkPubKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

const root = document.getElementById("root");
if (!root) throw new Error("Root element not found");

createRoot(root).render(
  <StrictMode>
    {clerkPubKey ? (
      <ClerkProvider publishableKey={clerkPubKey}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ClerkProvider>
    ) : (
      <div className="min-h-screen bg-gray-50 px-6 py-10 text-gray-900">
        <div className="mx-auto max-w-2xl rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <h1 className="mb-2 text-xl font-semibold">Dashboard misconfigured</h1>
          <p className="mb-4 text-sm text-gray-700">
            This build is missing <code className="font-mono">VITE_CLERK_PUBLISHABLE_KEY</code>,
            so authentication can’t initialize.
          </p>
          <div className="rounded-md bg-gray-100 px-3 py-2 text-sm">
            <div className="font-mono">
              VITE_CLERK_PUBLISHABLE_KEY=pk_live_…
            </div>
          </div>
          <p className="mt-4 text-sm text-gray-700">
            Rebuild and redeploy the Static Web App with the correct Vite env vars.
          </p>
        </div>
      </div>
    )}
  </StrictMode>,
);
