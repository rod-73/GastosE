/**
 * GastosE Frontend Application
 */
const api = new GastosEAPI();

// DOM Elements
const loginBtn = document.getElementById('login-btn');
const logoutBtn = document.getElementById('logout-btn');
const loginSection = document.getElementById('login-section');
const appSection = document.getElementById('app-section');
const loginForm = document.getElementById('login-form');
const loginError = document.getElementById('login-error');
const fileInput = document.getElementById('file-input');
const uploadBtn = document.getElementById('upload-btn');

// Tab management
const tabs = document.querySelectorAll('.tab');
const tabContents = document.querySelectorAll('.tab-content');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Check if already logged in
    const savedToken = localStorage.getItem('gastose_token');
    if (savedToken) {
        api.setToken(savedToken);
        showApp();
        loadDocuments();
        loadExpenses();
        loadSuppliers();
    }

    // Login form
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;

        try {
            await api.login(username, password);
            localStorage.setItem('gastose_token', api.getToken());
            loginError.style.display = 'none';
            loginError.textContent = '';
            showApp();
            loadDocuments();
            loadExpenses();
            loadSuppliers();
        } catch (error) {
            loginError.textContent = error.message;
            loginError.style.display = 'block';
        }
    });

    // Logout
    logoutBtn.addEventListener('click', async () => {
        try {
            await api.logout();
        } finally {
            localStorage.removeItem('gastose_token');
            showLogin();
        }
    });

    // Tab switching
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const tabId = tab.dataset.tab;
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            tabContents.forEach(content => {
                content.style.display = content.id === `${tabId}-tab` ? 'block' : 'none';
            });
        });
    });

    // Upload
    uploadBtn.addEventListener('click', async () => {
        const file = fileInput.files[0];
        if (!file) {
            alert('Selecciona un archivo');
            return;
        }

        try {
            const doc = await api.uploadDocument(file);
            alert(`Documento subido: ${doc.id}`);
            loadDocuments();
            fileInput.value = '';
        } catch (error) {
            alert(`Error: ${error.message}`);
        }
    });
});

function showLogin() {
    loginSection.style.display = 'block';
    appSection.style.display = 'none';
    loginBtn.style.display = 'inline-block';
    logoutBtn.style.display = 'none';
}

function showApp() {
    loginSection.style.display = 'none';
    appSection.style.display = 'block';
    loginBtn.style.display = 'none';
    logoutBtn.style.display = 'inline-block';
}

async function loadDocuments() {
    try {
        const data = await api.listDocuments();
        const docs = data.documents || data;
        const ul = document.getElementById('documents-ul');
        ul.innerHTML = docs.map(doc => `
            <li>
                <strong>${doc.safe_name || doc.original_filename || 'Documento'}</strong>
                <span class="badge badge-${doc.state}">${doc.state}</span>
                <small>${doc.format_detected} - ${new Date(doc.uploaded_at).toLocaleDateString()}</small>
            </li>
        `).join('') || '<li><em>Sin documentos</em></li>';
    } catch (error) {
        if (error.message.includes('login again')) {
            showLogin();
            loginError.textContent = error.message;
            loginError.style.display = 'block';
            return;
        }
        console.error('Error loading documents:', error);
    }
}

async function loadExpenses() {
    try {
        const data = await api.listExpenses();
        const expenses = data.expenses || data;
        const ul = document.getElementById('expenses-ul');
        ul.innerHTML = expenses.map(exp => `
            <li>
                <strong>${exp.document_number || 'Gasto'}</strong>
                <span class="badge badge-${exp.state}">${exp.state}</span>
                <small>${exp.currency} ${exp.total}</small>
            </li>
        `).join('') || '<li><em>Sin gastos</em></li>';
    } catch (error) {
        if (error.message.includes('login again')) {
            showLogin();
            loginError.textContent = error.message;
            loginError.style.display = 'block';
            return;
        }
        console.error('Error loading expenses:', error);
    }
}

async function loadSuppliers() {
    try {
        const data = await api.listSuppliers();
        const suppliers = data.suppliers || data;
        const ul = document.getElementById('suppliers-ul');
        ul.innerHTML = suppliers.map(sup => `
            <li>
                <strong>${sup.name}</strong>
                <small>${sup.nif || ''}</small>
            </li>
        `).join('') || '<li><em>Sin proveedores</em></li>';
    } catch (error) {
        if (error.message.includes('login again')) {
            showLogin();
            loginError.textContent = error.message;
            loginError.style.display = 'block';
            return;
        }
        console.error('Error loading suppliers:', error);
    }
}
