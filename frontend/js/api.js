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
        const response = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || `Login failed: ${response.status}`);
        }

        const data = await response.json();
        this.token = data.token;
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
