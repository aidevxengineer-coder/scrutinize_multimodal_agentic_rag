import { useEffect, useState } from "react";
import { fetchUserProjects, loginWithGoogle } from "../api/client";
import { useApp } from "../context/AppContext";
import { EyeLogo } from "./EyeLogo";

export function AuthView() {
  const { login, completeAuthentication } = useApp();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function finishAuthentication(token: string) {
    localStorage.setItem("scrutinize_access_token", token);
    const { projects } = await fetchUserProjects();
    const project = projects[0];
    if (!project) {
      completeAuthentication();
      return;
    }
    login(project.name, project.api_key ?? "", project.client_key, project.project_id, project.settings);
  }

  async function handleCredentialResponse(response: any) {
    setLoading(true);
    setError(null);
    try {
      const authResult = await loginWithGoogle(response.credential);
      await finishAuthentication(authResult.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Google authentication failed.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || "";
    if (!googleClientId) {
      console.warn("VITE_GOOGLE_CLIENT_ID is not configured.");
    }

    // Load the Google client library dynamically
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.onload = () => {
      const g = (window as any).google;
      if (g) {
        g.accounts.id.initialize({
          client_id: googleClientId,
          callback: handleCredentialResponse,
        });
        g.accounts.id.renderButton(
          document.getElementById("google-signin-button"),
          {
            theme: "filled_black",
            size: "large",
            width: 320,
            text: "signin_with",
            shape: "pill",
          }
        );
      }
    };
    document.body.appendChild(script);

    return () => {
      document.body.removeChild(script);
    };
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center px-4 bg-[var(--app-bg)]">
      <div className="glass-panel w-full max-w-md space-y-8 rounded-3xl p-10 text-center">
        <div className="mx-auto flex items-center justify-center">
          <EyeLogo size={48} gap={8} />
        </div>
        <div>
          <h1 className="mt-5 text-3xl font-extrabold text-[var(--app-text)] tracking-tight">
            Welcome to Scrutinize
          </h1>
          <p className="mt-3 text-sm text-[var(--app-text-muted)]">
            Sign in to access your projects, files, and conversations.
          </p>
        </div>

        {error && (
          <div className="rounded-xl bg-[var(--app-danger-bg)] border border-[var(--app-border-strong)] p-4 text-sm text-[var(--app-danger)]">
            {error}
          </div>
        )}

        <div className="flex flex-col items-center justify-center py-4">
          {loading ? (
            <div className="flex items-center space-x-2 text-[var(--app-text-muted)]">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-[var(--app-text-muted)] border-t-transparent"></div>
              <span>Signing you in...</span>
            </div>
          ) : (
            <div id="google-signin-button"></div>
          )}
        </div>

        <div className="text-xs text-[var(--app-text-faint)]">
          By signing in, you agree to our Terms of Service and Privacy Policy.
        </div>
      </div>
    </div>
  );
}

