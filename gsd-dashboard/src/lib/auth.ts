import { useAuth } from "@clerk/clerk-react";
import { useCallback } from "react";

const JWT_TEMPLATE = import.meta.env.VITE_GSD_CLERK_JWT_TEMPLATE || "gsd";

/**
 * Hook that returns a function to get the current GSD JWT token.
 * Returns null if Clerk is not configured or user is not signed in.
 */
export function useGsdToken(): () => Promise<string | null> {
  let getToken: ((opts?: { template?: string }) => Promise<string | null>) | null = null;

  try {
    const auth = useAuth();
    getToken = auth.getToken;
  } catch {
    // Clerk not available (e.g., embedded mode without ClerkProvider)
  }

  return useCallback(async () => {
    if (!getToken) return null;
    const templated = await getToken({ template: JWT_TEMPLATE });
    if (templated) return templated;
    // Fallback to default session token if the named template isn't configured in Clerk.
    return getToken();
  }, [getToken]);
}
