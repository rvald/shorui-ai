/**
 * API client for user authentication.
 */

export interface User {
    user_id: string;
    email: string;
    tenant_id: string;
    role: string;
}

export interface LoginResponse {
    access_token: string;
    expires_in: number;
    user: User;
}

export interface RegisterResponse {
    user_id: string;
    email: string;
    tenant_id: string;
}

const API_URL = import.meta.env.VITE_RAG_API_URL || "http://localhost:8082";

export const authApi = {
    /**
     * Register a new user.
     */
    async register(
        email: string,
        password: string,
        tenantName: string
    ): Promise<RegisterResponse> {
        const response = await fetch(`${API_URL}/auth/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                email,
                password,
                tenant_name: tenantName,
            }),
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            if (response.status === 409) {
                throw new Error("Email already registered");
            }
            throw new Error(error.detail || "Registration failed");
        }

        return response.json();
    },

    /**
     * Login with email and password.
     * Sets HttpOnly refresh cookie automatically.
     */
    async login(email: string, password: string): Promise<LoginResponse> {
        const response = await fetch(`${API_URL}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include", // Required for cookies
            body: JSON.stringify({ email, password }),
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || "Invalid email or password");
        }

        return response.json();
    },

    /**
     * Refresh access token using HttpOnly cookie.
     */
    async refresh(): Promise<{ access_token: string; expires_in: number }> {
        const response = await fetch(`${API_URL}/auth/refresh`, {
            method: "POST",
            credentials: "include",
        });

        if (!response.ok) {
            throw new Error("Token refresh failed");
        }

        return response.json();
    },

    /**
     * Logout and revoke all tokens.
     */
    async logout(accessToken: string): Promise<void> {
        await fetch(`${API_URL}/auth/logout`, {
            method: "POST",
            headers: {
                Authorization: `Bearer ${accessToken}`,
            },
            credentials: "include",
        });
    },

    /**
     * Get current user info.
     */
    async getMe(accessToken: string): Promise<User> {
        const response = await fetch(`${API_URL}/auth/me`, {
            headers: {
                Authorization: `Bearer ${accessToken}`,
            },
        });

        if (!response.ok) {
            throw new Error("Failed to get user info");
        }

        return response.json();
    },
};
