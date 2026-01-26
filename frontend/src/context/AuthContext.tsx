/**
 * Authentication context for React app.
 * Manages user state, access tokens, and auto-refresh.
 */

import {
    createContext,
    useContext,
    useState,
    useEffect,
    useCallback,
    type ReactNode,
} from "react";
import { authApi, type User } from "@/api/authApi";

interface AuthState {
    user: User | null;
    accessToken: string | null;
    isAuthenticated: boolean;
    isLoading: boolean;
}

interface AuthContextType extends AuthState {
    login: (email: string, password: string) => Promise<void>;
    register: (
        email: string,
        password: string,
        tenantName: string
    ) => Promise<void>;
    logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function useAuth(): AuthContextType {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error("useAuth must be used within an AuthProvider");
    }
    return context;
}

interface AuthProviderProps {
    children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
    const [state, setState] = useState<AuthState>({
        user: null,
        accessToken: null,
        isAuthenticated: false,
        isLoading: true,
    });

    // Try to restore session on mount
    useEffect(() => {
        const restoreSession = async () => {
            try {
                // Try to refresh token (if cookie exists)
                const { access_token } = await authApi.refresh();
                const user = await authApi.getMe(access_token);
                setState({
                    user,
                    accessToken: access_token,
                    isAuthenticated: true,
                    isLoading: false,
                });
            } catch {
                // No valid session
                setState({
                    user: null,
                    accessToken: null,
                    isAuthenticated: false,
                    isLoading: false,
                });
            }
        };

        restoreSession();
    }, []);

    // Auto-refresh token before expiry
    useEffect(() => {
        if (!state.isAuthenticated || !state.accessToken) return;

        // Refresh 1 minute before expiry (assuming 15 min TTL)
        const refreshInterval = setInterval(
            async () => {
                try {
                    const { access_token } = await authApi.refresh();
                    setState((prev) => ({
                        ...prev,
                        accessToken: access_token,
                    }));
                } catch {
                    // Refresh failed, logout
                    setState({
                        user: null,
                        accessToken: null,
                        isAuthenticated: false,
                        isLoading: false,
                    });
                }
            },
            14 * 60 * 1000
        ); // 14 minutes

        return () => clearInterval(refreshInterval);
    }, [state.isAuthenticated, state.accessToken]);

    const login = useCallback(async (email: string, password: string) => {
        const response = await authApi.login(email, password);
        setState({
            user: response.user,
            accessToken: response.access_token,
            isAuthenticated: true,
            isLoading: false,
        });
    }, []);

    const register = useCallback(
        async (email: string, password: string, tenantName: string) => {
            await authApi.register(email, password, tenantName);
            // Auto-login after registration
            await login(email, password);
        },
        [login]
    );

    const logout = useCallback(async () => {
        try {
            if (state.accessToken) {
                await authApi.logout(state.accessToken);
            }
        } catch {
            // Ignore logout errors
        }
        setState({
            user: null,
            accessToken: null,
            isAuthenticated: false,
            isLoading: false,
        });
    }, [state.accessToken]);

    return (
        <AuthContext.Provider
            value={{
                ...state,
                login,
                register,
                logout,
            }}
        >
            {children}
        </AuthContext.Provider>
    );
}
