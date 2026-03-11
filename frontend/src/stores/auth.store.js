// src/stores/auth.store.js
import { writable } from 'svelte/store';

export const isAuthenticated = writable(false);
export const authToken = writable(null);
export const authUser = writable(null);
export const authError = writable(null);
export const tokenExpiry = writable(null);

export async function initAuth() {
    const token = localStorage.getItem('auth_token');
    const user = localStorage.getItem('auth_user');
    const expiry = localStorage.getItem('token_expiry');
    
    // Check if token exists and hasn't expired client-side
    if (token && user && expiry) {
        const now = Math.floor(Date.now() / 1000);
        if (now < parseInt(expiry)) {
            // Validate token with server
            try {
                const response = await fetch('/api/validate', {
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                });
                
                if (response.ok) {
                    authToken.set(token);
                    authUser.set(user);
                    tokenExpiry.set(parseInt(expiry));
                    isAuthenticated.set(true);
                } else {
                    // Token invalid on server, clear storage
                    logout();
                }
            } catch (error) {
                // Network error, clear to be safe
                logout();
            }
        } else {
            // Token expired, clear storage
            logout();
        }
    }
}

export async function login(username, password) {
    authError.set(null);
    
    try {
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Login failed');
        }
        
        // Calculate expiry timestamp
        const expiryTime = Math.floor(Date.now() / 1000) + data.expires_in;
        
        // Store token and expiry
        localStorage.setItem('auth_token', data.token);
        localStorage.setItem('auth_user', data.username);
        localStorage.setItem('token_expiry', expiryTime.toString());
        
        authToken.set(data.token);
        authUser.set(data.username);
        tokenExpiry.set(expiryTime);
        isAuthenticated.set(true);
        
        return { success: true };
    } catch (error) {
        authError.set(error.message);
        return { success: false, error: error.message };
    }
}

export function logout() {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('auth_user');
    localStorage.removeItem('token_expiry');
    
    authToken.set(null);
    authUser.set(null);
    tokenExpiry.set(null);
    isAuthenticated.set(false);
}

export function getAuthHeaders() {
    let token;
    authToken.subscribe(value => token = value)();
    
    return token ? {
        'Authorization': `Bearer ${token}`
    } : {};
}