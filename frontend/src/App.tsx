import type { Message } from "@langchain/langgraph-sdk";
import { useState, useEffect, useRef, useCallback } from "react";
import { Routes, Route } from "react-router-dom";
import { WelcomeScreen } from "@/components/WelcomeScreen";
import { AgentChatView } from "@/components/AgentChatView";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { Button } from "@/components/ui/button";
import { agentApi } from "@/api/agentApi";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import LoginPage from "@/pages/Login";
import RegisterPage from "@/pages/Register";

/**
 * Main chat view component (authenticated).
 */
function ChatView() {
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const { user, accessToken, logout } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Create agent session on mount
  useEffect(() => {
    if (!sessionId && accessToken) {
      agentApi
        .createSession(accessToken)
        .then((session) => {
          setSessionId(session.session_id);
        })
        .catch((err) => {
          console.error("Failed to create agent session:", err);
          setError("Failed to create agent session");
        });
    }
  }, [sessionId, accessToken]);

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollAreaRef.current) {
      const scrollViewport = scrollAreaRef.current.querySelector(
        "[data-radix-scroll-area-viewport]"
      );
      if (scrollViewport) {
        scrollViewport.scrollTop = scrollViewport.scrollHeight;
      }
    }
  }, [messages]);

  // Message submit handler
  const handleSubmit = useCallback(
    async (submittedInputValue: string, files: File[]) => {
      if (!submittedInputValue.trim() && files.length === 0) return;
      if (!sessionId) {
        setError("No agent session. Please refresh.");
        return;
      }
      if (!accessToken) {
        setError("Authentication token missing. Please login again.");
        return;
      }

      setIsLoading(true);
      setError(null);

      // Build user message content (include file names if present)
      let displayContent = submittedInputValue;
      if (files.length > 0) {
        const fileNames = files.map((f) => f.name).join(", ");
        displayContent += displayContent
          ? `\n\n📎 ${fileNames}`
          : `📎 ${fileNames}`;
      }

      const userMsg: Message = {
        type: "human",
        content: displayContent,
        id: Date.now().toString(),
      };

      setMessages((prev) => [...prev, userMsg]);

      try {
        const response = await agentApi.sendMessage(
          sessionId,
          submittedInputValue ||
          "Please analyze the uploaded file(s) for HIPAA compliance.",
          "default",
          files.length > 0 ? files : undefined,
          accessToken
        );

        const aiMsgId = (Date.now() + 1).toString();

        setMessages((prev) => [
          ...prev,
          {
            type: "ai",
            content: response.content,
            id: aiMsgId,
            additional_kwargs: { steps: response.steps },
          },
        ]);
      } catch (err: any) {
        if (err.message.includes("expired")) {
          // Session expired, create new one
          try {
            const newSession = await agentApi.createSession(accessToken);
            setSessionId(newSession.session_id);
            setMessages([]);
            setError("Session expired. Started new session. Please try again.");
          } catch {
            setError("Failed to create new session");
          }
        } else {
          setError(err.message);
        }
      } finally {
        setIsLoading(false);
      }
    },
    [sessionId, accessToken]
  );

  const handleCancel = useCallback(() => {
    setIsLoading(false);
  }, []);

  const handleNewSession = useCallback(() => {
    setError(null);
    setMessages([]);
    setSessionId(null);
  }, []);

  const handleLogout = useCallback(async () => {
    await logout();
  }, [logout]);

  return (
    <div className="flex h-screen bg-neutral-800 text-neutral-100 font-sans antialiased">
      <main className="h-full w-full max-w-4xl mx-auto flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-neutral-700">
          <h1 className="text-lg font-semibold text-neutral-100">
            🩺 HIPAA Compliance Assistant
          </h1>
          <div className="flex items-center gap-3">
            {user && (
              <span className="text-sm text-neutral-400 hidden sm:inline">
                {user.email}
              </span>
            )}
            {messages.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleNewSession}
                className="text-neutral-400 hover:text-neutral-100"
              >
                New Session
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={handleLogout}
              className="text-neutral-400 hover:text-neutral-100"
            >
              Logout
            </Button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto">
          {messages.length === 0 && !error ? (
            <WelcomeScreen
              handleSubmit={handleSubmit}
              isLoading={isLoading}
              onCancel={handleCancel}
            />
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-full">
              <div className="flex flex-col items-center justify-center gap-4">
                <h1 className="text-2xl text-red-400 font-bold">Error</h1>
                <p className="text-red-400">{error}</p>
                <Button variant="destructive" onClick={handleNewSession}>
                  Start New Session
                </Button>
              </div>
            </div>
          ) : (
            <AgentChatView
              messages={messages}
              isLoading={isLoading}
              scrollAreaRef={scrollAreaRef}
              onSubmit={handleSubmit}
              onCancel={handleCancel}
            />
          )}
        </div>
      </main>
    </div>
  );
}

/**
 * App root with routing.
 */
export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <ChatView />
            </ProtectedRoute>
          }
        />
      </Routes>
    </AuthProvider>
  );
}
