/**
 * GastosE API Client
 */
const API_BASE = '/api/v1';

class GastosEAPI {
    constructor() {
        this.token = null;
    }

    setToken(token) {
        this.token = token;
    }

    getToken() {
        return this.token;
    }

    async request(method, path, body = null) {
        const headers = {
            'Content-Type': 'application/json',
        };

        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }

        const options = {
            method,
            headers,
        };

        if (body) {
            options.body = JSON.stringify(body);
        }

        const response = await fetch(`${API_BASE}${path}`, options);

        // Token expired/invalid: clear and force re-login
        if (response.status === 401) {
            this.token = null;
            localStorage.removeItem('gastose_token');
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || 'Session expired. Please login again.');
        }

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || `HTTP ${response.status}`);
        }

        if (response.status === 204) {
            return null;
        }

        return response.json();
    }

    // Auth
    async login(username, password) {
        console.log('[GastosE] Login attempt:', username, 'API_BASE:', API_BASE);
        const url = `${API_BASE}/auth/login`;
        console.log('[GastosE] Fetching URL:', url);
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });

        console.log('[GastosE] Login response status:', response.status);
        console.log('[GastosE] Login response headers:', Object.fromEntries(response.headers.entries()));
        const text = await response.text();
        console.log('[GastosE] Login response body:', text);

        if (!response.ok) {
            let detail = `Login failed: ${response.status}`;
            try {
                const error = JSON.parse(text);
                detail = error.detail || detail;
            } catch (e) {
                // not JSON
            }
            throw new Error(detail);
        }

        const data = JSON.parse(text);
        this.token = data.token;
        console.log('[GastosE] Login OK, token:', data.token.substring(0, 10) + '...');
        return data;
    }

    async logout() {
        await this.request('POST', '/auth/logout');
        this.token = null;
    }

    // Documents
    async uploadDocument(file) {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch(`${API_BASE}/documents`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.token}`,
            },
            body: formData,
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || `Upload failed: ${response.status}`);
        }

        return response.json();
    }

    async listDocuments() {
        return this.request('GET', '/documents');
    }

    async getDocument(id) {
        return this.request('GET', `/documents/${id}`);
    }

    async deleteDocument(id) {
        return this.request('DELETE', `/documents/${id}`);
    }

    // Expenses
    async listExpenses() {
        return this.request('GET', '/expenses');
    }

    async getExpense(id) {
        return this.request('GET', `/expenses/${id}`);
    }

    async getExpenseReview(id) {
        return this.request('GET', `/expenses/${id}/review`);
    }

    async acceptExpense(id) {
        return this.request('POST', `/expenses/${id}/accept`);
    }

    async rejectExpense(id, reason) {
        return this.request('POST', `/expenses/${id}/reject`, { reason });
    }

    // Suppliers
    async listSuppliers() {
        return this.request('GET', '/suppliers');
    }

    async createSupplier(data) {
        return this.request('POST', '/suppliers', data);
    }
}

// Export for use in app.js
window.GastosEAPI = GastosEAPI;
