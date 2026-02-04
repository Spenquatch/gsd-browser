import { useState, useCallback } from "react";
import { useAuth } from "@clerk/clerk-react";

/** Token lifetime options with their Clerk JWT template names */
const TOKEN_OPTIONS = [
  { label: "24 hours", template: "gsd-24h", seconds: 86400 },
  { label: "7 days", template: "gsd-7d", seconds: 604800 },
  { label: "30 days", template: "gsd-30d", seconds: 2592000 },
  { label: "6 months", template: "gsd-6m", seconds: 15552000 },
  { label: "1 year", template: "gsd-1y", seconds: 31536000 },
] as const;

type TokenOption = (typeof TOKEN_OPTIONS)[number];

export function TokensPage() {
  const { getToken } = useAuth();
  const [selectedOption, setSelectedOption] = useState<TokenOption>(TOKEN_OPTIONS[0]);
  const [generatedToken, setGeneratedToken] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleGenerate = useCallback(async () => {
    setGenerating(true);
    setError(null);
    setGeneratedToken(null);
    setCopied(false);

    try {
      const token = await getToken({ template: selectedOption.template });
      if (!token) {
        setError(
          `Failed to generate token. The JWT template "${selectedOption.template}" may not be configured in Clerk.`
        );
      } else {
        setGeneratedToken(token);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate token");
    } finally {
      setGenerating(false);
    }
  }, [getToken, selectedOption]);

  const handleCopy = useCallback(async () => {
    if (!generatedToken) return;
    try {
      await navigator.clipboard.writeText(generatedToken);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for browsers without clipboard API
      const textarea = document.createElement("textarea");
      textarea.value = generatedToken;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [generatedToken]);

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="mb-2 text-2xl font-bold text-gray-900">API Tokens</h1>
      <p className="mb-6 text-gray-600">
        Generate tokens to authenticate MCP clients with the GSD API.
      </p>

      {/* Token Generation Card */}
      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-lg font-semibold text-gray-900">Generate New Token</h2>

        <div className="mb-4">
          <label htmlFor="lifetime" className="mb-2 block text-sm font-medium text-gray-700">
            Token Lifetime
          </label>
          <select
            id="lifetime"
            value={selectedOption.template}
            onChange={(e) => {
              const option = TOKEN_OPTIONS.find((o) => o.template === e.target.value);
              if (option) setSelectedOption(option);
            }}
            className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-gsd-500 focus:outline-none focus:ring-1 focus:ring-gsd-500"
          >
            {TOKEN_OPTIONS.map((option) => (
              <option key={option.template} value={option.template}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={handleGenerate}
          disabled={generating}
          className="rounded-md bg-gsd-600 px-4 py-2 text-sm font-medium text-white hover:bg-gsd-700 focus:outline-none focus:ring-2 focus:ring-gsd-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {generating ? "Generating..." : "Generate Token"}
        </button>

        {error && (
          <div className="mt-4 rounded-md bg-red-50 p-4">
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {generatedToken && (
          <div className="mt-4">
            <label className="mb-2 block text-sm font-medium text-gray-700">
              Your Token (valid for {selectedOption.label})
            </label>
            <div className="relative">
              <textarea
                readOnly
                value={generatedToken}
                rows={4}
                className="block w-full rounded-md border border-gray-300 bg-gray-50 px-3 py-2 font-mono text-xs text-gray-900 focus:border-gsd-500 focus:outline-none focus:ring-1 focus:ring-gsd-500"
              />
              <button
                onClick={handleCopy}
                className="absolute right-2 top-2 rounded-md bg-white px-3 py-1 text-xs font-medium text-gray-700 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50"
              >
                {copied ? "Copied!" : "Copy"}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Security Warning */}
      <div className="mt-6 rounded-lg border border-yellow-200 bg-yellow-50 p-4">
        <div className="flex">
          <div className="flex-shrink-0">
            <svg
              className="h-5 w-5 text-yellow-400"
              viewBox="0 0 20 20"
              fill="currentColor"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z"
                clipRule="evenodd"
              />
            </svg>
          </div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-yellow-800">Security Notice</h3>
            <div className="mt-2 text-sm text-yellow-700">
              <ul className="list-inside list-disc space-y-1">
                <li>Tokens cannot be revoked once issued</li>
                <li>Store tokens securely (e.g., environment variables)</li>
                <li>Never commit tokens to version control</li>
                <li>Use the shortest lifetime that meets your needs</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      {/* Usage Instructions */}
      <div className="mt-6 rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-lg font-semibold text-gray-900">MCP Client Configuration</h2>

        <div className="space-y-4">
          <div>
            <h3 className="mb-2 text-sm font-medium text-gray-700">API Endpoint</h3>
            <code className="block rounded-md bg-gray-100 px-3 py-2 text-sm text-gray-900">
              https://gsd-prod-api.yellowplant-7a34cb33.eastus.azurecontainerapps.io/mcp
            </code>
          </div>

          <div>
            <h3 className="mb-2 text-sm font-medium text-gray-700">Environment Variable</h3>
            <pre className="overflow-x-auto rounded-md bg-gray-900 px-3 py-2 text-sm text-gray-100">
              {`export GSD_TOKEN="<your-token>"`}
            </pre>
          </div>

          <div>
            <h3 className="mb-2 text-sm font-medium text-gray-700">Claude Code MCP Config</h3>
            <pre className="overflow-x-auto rounded-md bg-gray-900 px-3 py-2 text-sm text-gray-100">
              {`{
  "mcpServers": {
    "gsd": {
      "command": "npx",
      "args": ["-y", "mcp-remote",
        "https://gsd-prod-api.yellowplant-7a34cb33.eastus.azurecontainerapps.io/mcp",
        "--header", "Authorization:Bearer \${GSD_TOKEN}"
      ]
    }
  }
}`}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}
