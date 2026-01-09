/**
 * API client for agent chat with ephemeral session management.
 */

export interface AgentSession {
    session_id: string;
    created_at: string;
}

export interface AgentStep {
    step_number: number;
    thought: string | null;
    action: string | null;
    observation: string | null;
}

export interface AgentResponse {
    content: string;
    steps: AgentStep[];
}

const AGENT_API_URL =
    import.meta.env.VITE_RAG_API_URL || "http://localhost:8082";

export const agentApi = {
    /**
     * Create a new agent session.
     */
    async createSession(): Promise<AgentSession> {
        const response = await fetch(`${AGENT_API_URL}/agent/sessions`, {
            method: "POST",
        });
        if (!response.ok) {
            throw new Error("Failed to create session");
        }
        return response.json();
    },

    /**
     * Send a message to an existing agent session.
     * Optionally include files for the agent to analyze.
     */
    async sendMessage(
        sessionId: string,
        message: string,
        projectId: string = "default",
        files?: File[]
    ): Promise<AgentResponse> {
        const formData = new FormData();
        formData.append("message", message);
        formData.append("project_id", projectId);

        if (files && files.length > 0) {
            files.forEach((file) => {
                formData.append("files", file);
            });
        }

        const response = await fetch(
            `${AGENT_API_URL}/agent/sessions/${sessionId}/messages`,
            {
                method: "POST",
                body: formData,
            }
        );
        if (!response.ok) {
            if (response.status === 404) {
                throw new Error("Session expired or not found");
            }
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || "Failed to send message");
        }
        return response.json();
    },
};
