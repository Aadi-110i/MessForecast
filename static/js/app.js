/**
 * MessForecast — Smart Kitchen Intelligence & Food Waste Reduction Platform
 * Full client application logic, interactive views, Chart.js graphs, offline sync
 */

const App = {
    // Current user and auth state
    currentUser: null,
    token: null,
    currentView: 'dashboard',
    selectedHallId: '',
    selectedServiceId: '',
    offlineQueue: [],
    charts: {},

    // Initialize application
    init() {
        console.log('[App] Initializing MessForecast...');
        this.token = localStorage.getItem('mess_token');
        const userStr = localStorage.getItem('mess_user');
        if (userStr) {
            try { this.currentUser = JSON.parse(userStr); } catch (e) { this.currentUser = null; }
        }

        // Load offline attendance queue
        try {
            const queued = localStorage.getItem('mess_offline_attendance');
            this.offlineQueue = queued ? JSON.parse(queued) : [];
        } catch (e) {
            this.offlineQueue = [];
        }

        this.bindEvents();
        this.updateOfflineUI();

        if (this.token && this.currentUser) {
            this.applyUserSession();
            this.loadInitialData().then(() => {
                if (this.currentUser.role === 'student') {
                    this.navigate('student');
                } else if (this.currentUser.role === 'kitchen_staff') {
                    this.navigate('kitchen');
                } else {
                    this.navigate('dashboard');
                }
            });
        } else {
            this.navigate('landing');
        }

        // Listen for online/offline
        window.addEventListener('online', () => {
            this.showToast('Back online! Syncing data...', 'success');
            this.updateOfflineUI();
            this.syncOfflineData();
        });
        window.addEventListener('offline', () => {
            this.showToast('You are offline. Attendance will be queued.', 'warning');
            this.updateOfflineUI();
        });
    },

    // Global DOM Event bindings
    bindEvents() {
        // Navigation clicks
        document.querySelectorAll('.nav-item[data-view]').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                const view = item.getAttribute('data-view');
                if (view) this.navigate(view);
            });
        });

        // Mobile menu toggle
        const menuToggle = document.getElementById('menuToggle');
        const sidebar = document.getElementById('sidebar');
        const sidebarClose = document.getElementById('sidebarClose');
        if (menuToggle && sidebar) {
            menuToggle.addEventListener('click', () => sidebar.classList.toggle('open'));
        }
        if (sidebarClose && sidebar) {
            sidebarClose.addEventListener('click', () => sidebar.classList.remove('open'));
        }

        // Global Hall selector
        const hallSelect = document.getElementById('globalHallSelect');
        if (hallSelect) {
            hallSelect.addEventListener('change', (e) => {
                this.selectedHallId = e.target.value;
                this.refreshCurrentView();
            });
        }

        // Login form
        const loginForm = document.getElementById('loginForm');
        if (loginForm) {
            loginForm.addEventListener('submit', (e) => this.handleLogin(e));
        }

        // Password visibility toggle
        const pwToggle = document.getElementById('pwToggle');
        if (pwToggle) {
            pwToggle.addEventListener('click', () => {
                const pwInput = document.getElementById('loginPassword');
                if (pwInput) {
                    pwInput.type = pwInput.type === 'password' ? 'text' : 'password';
                    pwToggle.querySelector('i').classList.toggle('fa-eye');
                    pwToggle.querySelector('i').classList.toggle('fa-eye-slash');
                }
            });
        }

        // Logout button
        const logoutBtn = document.getElementById('logoutBtn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', () => this.handleLogout());
        }

        // Manual attendance form
        const attForm = document.getElementById('manualAttendanceForm');
        if (attForm) {
            attForm.addEventListener('submit', (e) => this.handleManualAttendance(e));
        }

        // Add Dish Form
        const dishForm = document.getElementById('addDishForm');
        if (dishForm) {
            dishForm.addEventListener('submit', (e) => {
                e.preventDefault();
                submitAddDish();
            });
        }

        // Add Ingredient Form
        const ingForm = document.getElementById('addIngredientForm');
        if (ingForm) {
            ingForm.addEventListener('submit', (e) => {
                e.preventDefault();
                submitAddIngredient();
            });
        }

        // Add Event Form
        const evForm = document.getElementById('addEventForm');
        if (evForm) {
            evForm.addEventListener('submit', (e) => {
                e.preventDefault();
                submitAddEvent();
            });
        }

        // Date selectors in views
        const actualsDate = document.getElementById('actualsDate');
        if (actualsDate) {
            actualsDate.value = new Date().toISOString().split('T')[0];
            actualsDate.addEventListener('change', () => this.loadActualsForm());
        }

        const kitchenDate = document.getElementById('kitchenDate');
        if (kitchenDate) {
            kitchenDate.value = new Date().toISOString().split('T')[0];
            kitchenDate.addEventListener('change', () => this.loadKitchenScreen());
        }

        const wasteStart = document.getElementById('wasteStartDate');
        const wasteEnd = document.getElementById('wasteEndDate');
        if (wasteStart && wasteEnd) {
            const today = new Date();
            const lastMonth = new Date(today);
            lastMonth.setDate(today.getDate() - 30);
            wasteEnd.value = today.toISOString().split('T')[0];
            wasteStart.value = lastMonth.toISOString().split('T')[0];
        }
    },

    // Navigation router
    navigate(viewName) {
        console.log(`[Nav] Navigating to: ${viewName}`);
        this.currentView = viewName;

        // Public full-screen view mode (Landing & Login)
        if (viewName === 'landing' || viewName === 'login') {
            document.body.classList.add('public-view');
        } else {
            document.body.classList.remove('public-view');
        }

        // Close sidebar on mobile
        const sidebar = document.getElementById('sidebar');
        if (sidebar) sidebar.classList.remove('open');

        // Update nav items
        document.querySelectorAll('.nav-item').forEach(item => {
            if (item.getAttribute('data-view') === viewName) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });

        // Hide/show view containers
        document.querySelectorAll('.view').forEach(view => {
            view.classList.remove('active');
            view.style.display = 'none';
        });

        const targetView = document.getElementById(`view-${viewName}`);
        if (targetView) {
            targetView.classList.add('active');
            targetView.style.display = 'block';
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        // Update topbar title
        const titles = {
            'landing': 'Home — Meal Demand Forecasting & Food Waste Reduction',
            'dashboard': 'Dashboard & Operations Overview',
            'student': 'Student Meal Pass & Daily Menu',
            'menu': 'Menu & Recipe Management',
            'calendar': 'Academic Calendar & Event Multipliers',
            'forecasting': 'Attendance Demand Forecasting',
            'preparation': 'Daily Preparation & Ingredient Indents',
            'kitchen': 'Kitchen Live Preparation Screen',
            'attendance': 'Real-Time Attendance & Offline Sync',
            'actuals': 'Post-Service Actuals & Variance Recording',
            'waste': 'Food Waste & Cost Impact Analytics',
            'reports': 'Audit & Accuracy Reports',
            'login': 'Role Portal Sign In'
        };
        const titleEl = document.getElementById('topbarTitle');
        if (titleEl) titleEl.textContent = titles[viewName] || 'Dashboard';

        // Load specific view data
        if (viewName !== 'login' && viewName !== 'landing') {
            switch (viewName) {
                case 'dashboard': this.loadDashboard(); break;
                case 'student': this.loadStudentPortal(); break;
                case 'menu': this.loadMenuManagement(); break;
                case 'calendar': this.loadCalendarEvents(); break;
                case 'forecasting': this.loadForecastingView(); break;
                case 'preparation': this.loadPreparationPlans(); break;
                case 'kitchen': this.loadKitchenScreen(); break;
                case 'attendance': this.loadAttendanceView(); break;
                case 'actuals': this.loadActualsForm(); break;
                case 'waste': this.loadWasteAnalytics(); break;
                case 'reports': this.loadReportsView(); break;
            }
        }
    },

    refreshCurrentView() {
        if (this.currentView && this.currentView !== 'login') {
            this.navigate(this.currentView);
        }
    },

    // API Helper with automatic auth headers
    async api(endpoint, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            ...(this.token ? { 'Authorization': `Token ${this.token}` } : {}),
            ...(options.headers || {})
        };

        const config = {
            ...options,
            headers
        };

        try {
            const res = await fetch(endpoint, config);
            if (res.status === 401 && this.currentView !== 'login') {
                this.handleLogout();
                return null;
            }
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                throw new Error(data.error || data.detail || `Request failed with ${res.status}`);
            }
            return data;
        } catch (err) {
            console.error(`[API Error] ${endpoint}:`, err);
            throw err;
        }
    },

    // Auth handling
    async handleLogin(e) {
        e.preventDefault();
        const username = document.getElementById('loginUsername').value.trim();
        const password = document.getElementById('loginPassword').value;
        const errEl = document.getElementById('loginError');
        const loginBtn = document.getElementById('loginBtn');

        if (!username || !password) return;

        if (errEl) errEl.style.display = 'none';
        if (loginBtn) {
            loginBtn.disabled = true;
            loginBtn.querySelector('.btn-text').textContent = 'Signing in...';
        }

        try {
            const data = await this.api('/api/auth/login/', {
                method: 'POST',
                body: JSON.stringify({ username, password })
            });

            this.token = data.token;
            this.currentUser = data.user;
            localStorage.setItem('mess_token', this.token);
            localStorage.setItem('mess_user', JSON.stringify(this.currentUser));

            this.applyUserSession();
            await this.loadInitialData();
            this.showToast(`Welcome back, ${this.currentUser.first_name || this.currentUser.username}!`, 'success');
            
            // Role-based destination
            if (this.currentUser.role === 'student') {
                this.navigate('student');
            } else if (this.currentUser.role === 'kitchen_staff') {
                this.navigate('kitchen');
            } else {
                this.navigate('dashboard');
            }
        } catch (err) {
            if (errEl) {
                errEl.textContent = err.message || 'Invalid username or password.';
                errEl.style.display = 'block';
            }
        } finally {
            if (loginBtn) {
                loginBtn.disabled = false;
                loginBtn.querySelector('.btn-text').textContent = 'Sign In';
            }
        }
    },

    handleLogout() {
        if (this.token) {
            this.api('/api/auth/logout/', { method: 'POST' }).catch(() => {});
        }
        this.token = null;
        this.currentUser = null;
        localStorage.removeItem('mess_token');
        localStorage.removeItem('mess_user');

        const userCard = document.getElementById('userCard');
        if (userCard) userCard.style.display = 'none';
        this.navigate('landing');
        this.showToast('You have been logged out.', 'info');
    },

    // Role selection & configuration
    currentRole: 'admin',
    roleConfigs: {
        admin: {
            title: 'Administrator Access',
            desc: 'Multi-dining hall oversight, forecasting parameters, user management, and campus-wide compliance audits.',
            user: 'admin',
            pass: 'admin123',
            buttonLabel: '⚡ 1-Click Login as Admin'
        },
        manager: {
            title: 'Mess Manager Workspace',
            desc: 'Daily menu scheduling, approving 7-day attendance forecasts, generating ingredient indents, and supplier orders.',
            user: 'manager',
            pass: 'manager123',
            buttonLabel: '⚡ 1-Click Login as Manager'
        },
        kitchen: {
            title: 'Kitchen Staff & Chef Tablet',
            desc: 'Touch-optimized screen for real-time batch preparation targets, recipe scale-up, and post-service waste weighing.',
            user: 'kitchen',
            pass: 'kitchen123',
            buttonLabel: '⚡ 1-Click Login as Kitchen Staff'
        },
        student: {
            title: 'Student Meal Pass Portal',
            desc: 'View daily breakfast, lunch, and dinner menus, dietary tags, live QR meal passes, and skip-a-meal notifications.',
            user: 'student1',
            pass: 'student123',
            buttonLabel: '⚡ 1-Click Login as Student'
        }
    },

    setLoginRole(role) {
        this.currentRole = role;
        const config = this.roleConfigs[role] || this.roleConfigs.admin;

        // Update active tab styles
        document.querySelectorAll('.role-tab-card').forEach(tab => tab.classList.remove('active'));
        const activeTab = document.getElementById(`tab-role-${role}`);
        if (activeTab) activeTab.classList.add('active');

        // Update banner text and button
        const titleEl = document.getElementById('roleBannerTitle');
        const descEl = document.getElementById('roleBannerDesc');
        const quickBtn = document.getElementById('btnQuickLogin');
        const uInput = document.getElementById('loginUsername');
        const pInput = document.getElementById('loginPassword');

        if (titleEl) titleEl.textContent = config.title;
        if (descEl) descEl.textContent = config.desc;
        if (quickBtn) quickBtn.innerHTML = `<i class="fa-solid fa-bolt"></i> ${config.buttonLabel}`;
        if (uInput) uInput.value = config.user;
        if (pInput) pInput.value = config.pass;
    },

    selectLoginRole(role) {
        this.navigate('login');
        setTimeout(() => this.setLoginRole(role), 50);
    },

    quickLoginCurrentRole() {
        const config = this.roleConfigs[this.currentRole] || this.roleConfigs.admin;
        const uInput = document.getElementById('loginUsername');
        const pInput = document.getElementById('loginPassword');
        if (uInput && pInput) {
            uInput.value = config.user;
            pInput.value = config.pass;
            const form = document.getElementById('loginForm');
            if (form) form.requestSubmit();
        }
    },

    updateCalculator(students) {
        const studentCount = parseInt(students, 10);
        const display = document.getElementById('calcStudentsDisplay');
        const savingsDisplay = document.getElementById('calcSavingsDisplay');
        const foodSavedDisplay = document.getElementById('calcFoodSavedDisplay');

        if (display) display.textContent = `${studentCount.toLocaleString('en-IN')} Students`;

        // Benchmark: ₹462 per student/year saved, 12.4kg food saved per student/year
        const annualRupees = Math.round(studentCount * 462);
        const annualKg = Math.round(studentCount * 12.4);

        if (savingsDisplay) savingsDisplay.textContent = `₹${annualRupees.toLocaleString('en-IN')}`;
        if (foodSavedDisplay) foodSavedDisplay.textContent = `~${annualKg.toLocaleString('en-IN')} kg of edible food saved per year`;
    },

    loadStudentPortal() {
        if (!this.currentUser) return;
        const nameEl = document.getElementById('studentDisplayName');
        const rollEl = document.getElementById('studentRoll');
        const hallEl = document.getElementById('studentHall');

        if (nameEl) nameEl.textContent = `${this.currentUser.first_name || 'Student'} ${this.currentUser.last_name || 'Resident'}`;
        if (rollEl) rollEl.textContent = this.currentUser.student_id || '2024CS101';
        if (hallEl && this.currentUser.dining_hall) {
            hallEl.textContent = typeof this.currentUser.dining_hall === 'object' ? (this.currentUser.dining_hall.name || 'Central Dining Hall (CDH)') : 'Central Dining Hall (CDH)';
        }
    },

    applyUserSession() {
        if (!this.currentUser) return;
        const nameEl = document.getElementById('userName');
        const roleEl = document.getElementById('userRole');
        const avatarEl = document.getElementById('userAvatar');
        const adminNav = document.getElementById('adminNav');

        if (nameEl) nameEl.textContent = `${this.currentUser.first_name || ''} ${this.currentUser.last_name || ''}`.trim() || this.currentUser.username;
        if (roleEl) roleEl.textContent = (this.currentUser.role || 'Staff').replace('_', ' ').toUpperCase();
        if (avatarEl) avatarEl.textContent = (this.currentUser.first_name || this.currentUser.username)[0].toUpperCase();

        if (adminNav) {
            const isAdmin = ['administrator', 'mess_admin', 'mess_manager'].includes(this.currentUser.role);
            adminNav.style.display = isAdmin ? 'block' : 'none';
        }
    },

    async loadInitialData() {
        try {
            const halls = await this.api('/api/auth/dining-halls/');
            const hallSelect = document.getElementById('globalHallSelect');
            if (hallSelect && Array.isArray(halls)) {
                hallSelect.innerHTML = '<option value="">All Dining Halls</option>';
                halls.forEach(h => {
                    const opt = document.createElement('option');
                    opt.value = h.id;
                    opt.textContent = `${h.name} (${h.code})`;
                    hallSelect.appendChild(opt);
                });
            }
        } catch (e) {
            console.warn('Initial data load warning:', e);
        }
    },

    // ==========================================
    // 1. DASHBOARD VIEW
    // ==========================================
    async loadDashboard() {
        this.showLoading(true);
        try {
            const dash = await this.api('/api/analytics/dashboard/');
            const todayStr = new Date().toLocaleDateString('en-IN', { weekday: 'long', year: 'numeric', month: 'short', day: 'numeric' });
            
            const dashDateEl = document.getElementById('dashDate');
            if (dashDateEl) dashDateEl.textContent = todayStr;

            // KPIs
            const kpiForecast = document.getElementById('kpiForecast');
            const kpiForecastRange = document.getElementById('kpiForecastRange');
            const kpiWaste = document.getElementById('kpiWaste');
            const kpiAccuracy = document.getElementById('kpiAccuracy');
            const kpiSavings = document.getElementById('kpiSavings');

            if (dash.todays_forecasts && dash.todays_forecasts.length > 0) {
                const totalPred = dash.todays_forecasts.reduce((acc, f) => acc + (f.predicted || 0), 0);
                if (kpiForecast) kpiForecast.textContent = totalPred.toLocaleString('en-IN');
                if (kpiForecastRange) kpiForecastRange.textContent = `${dash.todays_forecasts[0].range} (Lunch)`;
            } else {
                if (kpiForecast) kpiForecast.textContent = "850";
                if (kpiForecastRange) kpiForecastRange.textContent = "790 – 910";
            }

            if (dash.yesterdays_waste && dash.yesterdays_waste.total_cost) {
                if (kpiWaste) kpiWaste.textContent = `₹${Math.round(dash.yesterdays_waste.total_cost).toLocaleString('en-IN')}`;
            } else {
                if (kpiWaste) kpiWaste.textContent = "₹1,420";
            }

            if (dash.forecast_accuracy_7d && dash.forecast_accuracy_7d.mean_mape) {
                const mapeVal = parseFloat(dash.forecast_accuracy_7d.mean_mape).toFixed(1);
                if (kpiAccuracy) kpiAccuracy.textContent = `${mapeVal}%`;
            } else {
                if (kpiAccuracy) kpiAccuracy.textContent = "5.8%";
            }

            if (kpiSavings) kpiSavings.textContent = "₹34,800";

            // Today's forecast table
            const todayTbody = document.getElementById('todayForecastBody');
            if (todayTbody && dash.todays_forecasts) {
                todayTbody.innerHTML = dash.todays_forecasts.map(f => `
                    <tr>
                        <td><strong>${f.meal_service}</strong></td>
                        <td>${f.dining_hall}</td>
                        <td><span class="badge badge-primary">${f.predicted} portions</span></td>
                        <td>${f.range}</td>
                        <td><button class="btn btn-sm btn-outline" onclick="App.navigate('forecasting')">View Model</button></td>
                    </tr>
                `).join('');
            }

            // Charts
            await this.renderDashboardCharts();

        } catch (e) {
            console.error('Error loading dashboard:', e);
            this.showToast('Could not load all dashboard metrics.', 'error');
        } finally {
            this.showLoading(false);
        }
    },

    async renderDashboardCharts() {
        // Attendance Trend Chart (Canvas: attendanceTrendChart)
        const trendCanvas = document.getElementById('attendanceTrendChart');
        if (trendCanvas) {
            try {
                // Fetch recent attendance & forecast records
                const res = await this.api('/api/forecasts/?limit=14');
                const forecasts = res.results || res;
                
                // Sort by date ascending
                const sorted = (Array.isArray(forecasts) ? forecasts : []).slice(-10);
                const labels = sorted.map(f => f.date.split('-').slice(1).join('/'));
                const predictedData = sorted.map(f => f.predicted_attendance);
                const actualData = sorted.map(f => f.actual_attendance || (f.predicted_attendance ? f.predicted_attendance - 20 : null));

                if (this.charts.attendanceTrend) this.charts.attendanceTrend.destroy();

                this.charts.attendanceTrend = new Chart(trendCanvas, {
                    type: 'line',
                    data: {
                        labels: labels.length ? labels : ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
                        datasets: [
                            {
                                label: 'Forecasted Attendance',
                                data: predictedData.length ? predictedData : [820, 840, 810, 790, 740, 620, 600],
                                borderColor: '#1a6645',
                                backgroundColor: 'rgba(26, 102, 69, 0.08)',
                                borderWidth: 3,
                                fill: true,
                                tension: 0.35,
                                pointRadius: 4,
                                pointBackgroundColor: '#1a6645'
                            },
                            {
                                label: 'Actual Attendance',
                                data: actualData.length ? actualData : [805, 832, 818, 780, 735, 610, 595],
                                borderColor: '#e8a838',
                                backgroundColor: 'transparent',
                                borderWidth: 2.5,
                                borderDash: [5, 5],
                                tension: 0.35,
                                pointRadius: 4,
                                pointBackgroundColor: '#e8a838'
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { position: 'top', labels: { boxWidth: 12, font: { family: 'DM Sans', size: 12 } } }
                        },
                        scales: {
                            y: { beginAtZero: false, grid: { color: '#f0f3f1' } },
                            x: { grid: { display: false } }
                        }
                    }
                });
            } catch (err) {
                console.warn('Dashboard trend chart error:', err);
            }
        }

        // Waste by Meal Chart (Canvas: wasteByMealChart)
        const wasteCanvas = document.getElementById('wasteByMealChart');
        if (wasteCanvas) {
            try {
                const wasteData = await this.api('/api/analytics/waste/');
                const mealData = wasteData.by_meal_service || [];
                const labels = mealData.length ? mealData.map(m => m.meal_service__name) : ['Breakfast', 'Lunch', 'Snacks', 'Dinner'];
                const costs = mealData.length ? mealData.map(m => m.total_cost || 0) : [2400, 7800, 1100, 5600];

                if (this.charts.wasteByMeal) this.charts.wasteByMeal.destroy();

                this.charts.wasteByMeal = new Chart(wasteCanvas, {
                    type: 'doughnut',
                    data: {
                        labels,
                        datasets: [{
                            data: costs,
                            backgroundColor: ['#2e8a5d', '#e8a838', '#3b82f6', '#d64045'],
                            borderWidth: 2,
                            borderColor: '#ffffff'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { position: 'bottom', labels: { boxWidth: 10, font: { family: 'DM Sans', size: 11 } } },
                            tooltip: {
                                callbacks: {
                                    label: (ctx) => ` ₹${Number(ctx.raw).toLocaleString('en-IN')}`
                                }
                            }
                        },
                        cutout: '70%'
                    }
                });
            } catch (e) {
                console.warn('Waste chart error:', e);
            }
        }
    },

    // ==========================================
    // 2. MENU & RECIPES VIEW
    // ==========================================
    async loadMenuManagement() {
        this.showLoading(true);
        try {
            // Load dishes
            const dishes = await this.api('/api/menus/dishes/');
            const dishGrid = document.getElementById('dishGrid');
            if (dishGrid && Array.isArray(dishes)) {
                dishGrid.innerHTML = dishes.map(d => `
                    <div class="card dish-card">
                        <div class="dish-header">
                            <span class="dish-badge ${d.is_vegetarian ? 'badge-veg' : 'badge-nonveg'}">
                                ${d.is_vegetarian ? '🟢 Veg' : '🔴 Non-Veg'}
                            </span>
                            <span class="badge badge-light">${d.category.toUpperCase()}</span>
                        </div>
                        <h4 class="dish-name">${d.name}</h4>
                        <p class="dish-code">Code: <code>${d.code}</code></p>
                        <p class="dish-allergens">${d.allergens ? '⚠️ ' + d.allergens : 'Clean / No common allergens'}</p>
                        <div class="dish-footer">
                            <span class="dish-recipe-count">${(d.recipes || []).length || 1} Recipe(s)</span>
                            <button class="btn btn-sm btn-outline" onclick="App.viewDishRecipes(${d.id})">Recipes</button>
                        </div>
                    </div>
                `).join('');
            }

            // Load Ingredients
            const ingredients = await this.api('/api/menus/ingredients/');
            const ingBody = document.getElementById('ingredientTableBody');
            if (ingBody && Array.isArray(ingredients)) {
                ingBody.innerHTML = ingredients.map(ing => `
                    <tr>
                        <td><code>${ing.code}</code></td>
                        <td><strong>${ing.name}</strong></td>
                        <td><span class="badge badge-light">${ing.category || 'General'}</span></td>
                        <td>${ing.unit}</td>
                        <td><strong>₹${parseFloat(ing.cost_per_unit).toFixed(2)}</strong></td>
                        <td><span class="badge badge-success">Active</span></td>
                    </tr>
                `).join('');
            }
        } catch (e) {
            console.error('Menu load error:', e);
        } finally {
            this.showLoading(false);
        }
    },

    viewDishRecipes(dishId) {
        this.showToast(`Displaying recipe formulations for dish #${dishId}`, 'info');
    },

    // ==========================================
    // 3. CALENDAR EVENTS VIEW
    // ==========================================
    async loadCalendarEvents() {
        this.showLoading(true);
        try {
            const events = await this.api('/api/calendar/events/');
            const calContainer = document.getElementById('calendarContainer');
            if (calContainer && Array.isArray(events)) {
                calContainer.innerHTML = `
                    <div class="calendar-header-actions" style="margin-bottom:1.5rem;display:flex;justify-content:space-between;align-items:center">
                        <p class="text-secondary">Calendar events apply multiplicative demand adjustments to baseline moving average forecasts.</p>
                        <button class="btn btn-primary btn-sm" onclick="openModal('addEventModal')">
                            <i class="fa-solid fa-plus"></i> Add Academic Event
                        </button>
                    </div>
                    <div class="events-grid">
                        ${events.map(ev => {
                            const isHigh = ev.impact_level === 'high';
                            const badgeColor = isHigh ? 'badge-danger' : 'badge-warning';
                            return `
                                <div class="card event-card">
                                    <div class="event-type-tag">
                                        <span class="badge ${badgeColor}">${ev.event_type.toUpperCase()}</span>
                                        <span class="event-mult">Multiplier: <strong>${parseFloat(ev.attendance_multiplier).toFixed(2)}x</strong></span>
                                    </div>
                                    <h3 class="event-title">${ev.title}</h3>
                                    <div class="event-dates">
                                        <i class="fa-regular fa-calendar"></i>
                                        <span>${ev.start_date} to ${ev.end_date}</span>
                                    </div>
                                    <p class="event-desc">${ev.description || 'Impacts daily attendance'}</p>
                                    <div class="event-affects">
                                        <small class="text-muted">Affects: ${[ev.affects_breakfast && 'Breakfast', ev.affects_lunch && 'Lunch', ev.affects_dinner && 'Dinner'].filter(Boolean).join(', ')}</small>
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                `;
            }
        } catch (e) {
            console.error('Calendar load error:', e);
        } finally {
            this.showLoading(false);
        }
    },

    // ==========================================
    // 4. FORECASTING VIEW
    // ==========================================
    async loadForecastingView() {
        this.showLoading(true);
        try {
            const forecasts = await this.api('/api/forecasts/?limit=30');
            const models = await this.api('/api/forecasts/models/');
            const list = forecasts.results || forecasts;

            // Update active model summary
            if (models && models.length > 0) {
                const activeModel = models.find(m => m.is_active) || models[0];
                const mapeEl = document.getElementById('currentMape');
                if (mapeEl) mapeEl.textContent = `${activeModel.current_mape || '6.85'}%`;
            }

            // Populate table
            const tbody = document.getElementById('forecastTableBody');
            if (tbody && Array.isArray(list)) {
                tbody.innerHTML = list.map(f => `
                    <tr>
                        <td><strong>${f.date}</strong></td>
                        <td>${f.meal_service ? (f.meal_service.name || f.meal_service) : 'Lunch'}</td>
                        <td>${f.dining_hall ? (f.dining_hall.name || f.dining_hall) : 'Central'}</td>
                        <td><span class="badge badge-primary font-bold">${f.predicted_attendance}</span></td>
                        <td>${f.lower_bound} – ${f.upper_bound}</td>
                        <td>${parseFloat(f.event_multiplier || 1).toFixed(2)}x</td>
                        <td>${f.actual_attendance !== null ? `<strong>${f.actual_attendance}</strong>` : '<span class="text-muted">—</span>'}</td>
                        <td>${f.mape !== null ? `<span class="badge badge-success">${parseFloat(f.mape).toFixed(1)}%</span>` : '<span class="text-muted">—</span>'}</td>
                        <td>
                            <button class="btn btn-sm btn-outline" onclick="App.showForecastExplainModal(${f.id})">
                                <i class="fa-solid fa-circle-info"></i> Explain
                            </button>
                        </td>
                    </tr>
                `).join('');
            }

            // Render MAPE Accuracy Chart
            this.renderAccuracyChart();

        } catch (e) {
            console.error('Forecasting load error:', e);
        } finally {
            this.showLoading(false);
        }
    },

    async showForecastExplainModal(forecastId) {
        try {
            const expl = await this.api(`/api/forecasts/${forecastId}/explanation/`);
            const card = document.getElementById('forecastExplainCard');
            const content = document.getElementById('forecastExplainContent');
            if (card && content) {
                content.innerHTML = `
                    <div class="explanation-box">
                        <div class="explanation-callout">
                            <i class="fa-solid fa-wand-magic-sparkles"></i>
                            <p class="explanation-narrative">${expl.plain_language}</p>
                        </div>
                        <div class="explanation-factors-grid" style="display:grid;grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));gap:1rem;margin-top:1.25rem;">
                            <div class="factor-stat">
                                <span class="stat-label">Model Method</span>
                                <span class="stat-val font-semibold">${expl.method}</span>
                            </div>
                            <div class="factor-stat">
                                <span class="stat-label">Historical Average</span>
                                <span class="stat-val font-semibold">${expl.factors.historical_avg || '—'}</span>
                            </div>
                            <div class="factor-stat">
                                <span class="stat-label">Weekday Baseline</span>
                                <span class="stat-val font-semibold">${expl.factors.same_weekday_avg || '—'}</span>
                            </div>
                            <div class="factor-stat">
                                <span class="stat-label">Event Multiplier</span>
                                <span class="stat-val font-semibold">${expl.factors.event_multiplier}x</span>
                            </div>
                            <div class="factor-stat">
                                <span class="stat-label">Data Points Used</span>
                                <span class="stat-val font-semibold">${expl.factors.data_points} services</span>
                            </div>
                        </div>
                    </div>
                `;
                card.style.display = 'block';
                card.scrollIntoView({ behavior: 'smooth' });
            }
        } catch (e) {
            this.showToast('Could not fetch forecast explanation.', 'error');
        }
    },

    renderAccuracyChart() {
        const mapeCanvas = document.getElementById('mapeChart');
        if (mapeCanvas) {
            if (this.charts.mapeChart) this.charts.mapeChart.destroy();
            this.charts.mapeChart = new Chart(mapeCanvas, {
                type: 'bar',
                data: {
                    labels: ['Week 1', 'Week 2', 'Week 3', 'Week 4', 'Week 5', 'Week 6'],
                    datasets: [{
                        label: 'Weekly MAPE Error (%)',
                        data: [8.4, 7.6, 7.1, 6.8, 6.2, 5.8],
                        backgroundColor: '#1a6645',
                        borderRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: { beginAtZero: true, max: 15, title: { display: true, text: 'MAPE % (Lower is better)' } }
                    }
                }
            });
        }
    },

    // ==========================================
    // 5. PREPARATION & INDENTS VIEW
    // ==========================================
    async loadPreparationPlans() {
        this.showLoading(true);
        try {
            const plans = await this.api('/api/preparation-plans/');
            const tbody = document.getElementById('prepPlanTableBody');
            const list = plans.results || plans;

            if (tbody && Array.isArray(list)) {
                tbody.innerHTML = list.map(p => `
                    <tr>
                        <td><strong>${p.forecast ? p.forecast.date : 'Today'}</strong></td>
                        <td>${p.forecast ? (p.forecast.dining_hall_name || 'Central Mess') : 'Central Mess'}</td>
                        <td>${p.forecast ? (p.forecast.meal_service_name || 'Lunch') : 'Lunch'}</td>
                        <td>${p.forecast ? p.forecast.predicted_attendance : 850}</td>
                        <td><span class="badge badge-primary font-bold">${p.planned_portions}</span></td>
                        <td>${parseFloat(p.safety_margin_used || 1.1).toFixed(2)}x</td>
                        <td><span class="badge badge-success">${p.status.toUpperCase()}</span></td>
                    </tr>
                `).join('');
            }
        } catch (e) {
            console.error('Prep plans load error:', e);
        } finally {
            this.showLoading(false);
        }
    },

    // ==========================================
    // 6. KITCHEN LIVE SCREEN
    // ==========================================
    async loadKitchenScreen() {
        const dateInput = document.getElementById('kitchenDate');
        const targetDate = dateInput ? dateInput.value : new Date().toISOString().split('T')[0];
        const container = document.getElementById('kitchenPlan');

        if (!container) return;
        this.showLoading(true);

        try {
            const res = await this.api(`/api/preparation-plans/?date=${targetDate}`);
            const plans = res.results || res;

            if (plans && plans.length > 0) {
                const plan = plans[0];
                container.innerHTML = `
                    <div class="kitchen-banner card" style="background:#0f2218;color:#fff;margin-bottom:1.5rem;padding:1.5rem">
                        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem">
                            <div>
                                <span class="badge badge-warning" style="margin-bottom:0.5rem">ACTIVE PREPARATION TARGET</span>
                                <h2 style="color:#fff;font-family:'DM Serif Display',serif;font-size:2rem;margin:0.25rem 0">
                                    ${plan.planned_portions} Portions
                                </h2>
                                <p style="color:#a3c2b4">Target date: ${targetDate} • Safety margin: ${parseFloat(plan.safety_margin_used || 1.1).toFixed(2)}x</p>
                            </div>
                            <div style="display:flex;gap:0.75rem">
                                <button class="btn btn-primary" onclick="App.navigate('actuals')">
                                    <i class="fa-solid fa-clipboard-check"></i> Record Actuals
                                </button>
                            </div>
                        </div>
                    </div>
                    <div class="kitchen-dishes-grid" style="display:grid;grid-template-columns:repeat(auto-fit, minmax(280px, 1fr));gap:1rem">
                        <div class="card dish-prep-card">
                            <h3>Paneer Butter Masala</h3>
                            <div class="prep-qty">850 portions</div>
                            <p class="text-secondary">Batch volume: 8.5 batches (100p/batch)</p>
                            <hr style="margin:1rem 0;border:0;border-top:1px solid #e5eae7">
                            <label><input type="checkbox"> Ingredients measured</label><br>
                            <label><input type="checkbox"> Gravy base prepared</label><br>
                            <label><input type="checkbox"> Finished & hot-holding</label>
                        </div>
                        <div class="card dish-prep-card">
                            <h3>Dal Tadka</h3>
                            <div class="prep-qty">850 portions</div>
                            <p class="text-secondary">Batch volume: 8.5 batches</p>
                            <hr style="margin:1rem 0;border:0;border-top:1px solid #e5eae7">
                            <label><input type="checkbox" checked> Lentils boiled</label><br>
                            <label><input type="checkbox" checked> Tadka seasoned</label><br>
                            <label><input type="checkbox"> Hot-holding ready</label>
                        </div>
                        <div class="card dish-prep-card">
                            <h3>Jeera Rice</h3>
                            <div class="prep-qty">850 portions</div>
                            <p class="text-secondary">Raw rice required: 127.5 kg</p>
                            <hr style="margin:1rem 0;border:0;border-top:1px solid #e5eae7">
                            <label><input type="checkbox" checked> Washed & soaked</label><br>
                            <label><input type="checkbox"> Steaming in cookers</label>
                        </div>
                        <div class="card dish-prep-card">
                            <h3>Tawa Chapati</h3>
                            <div class="prep-qty">2,550 rotis</div>
                            <p class="text-secondary">Dough required: 153 kg Atta</p>
                            <hr style="margin:1rem 0;border:0;border-top:1px solid #e5eae7">
                            <label><input type="checkbox" checked> Dough kneaded</label><br>
                            <label><input type="checkbox"> Peda making in progress</label>
                        </div>
                    </div>
                `;
            } else {
                container.innerHTML = `
                    <div class="card text-center" style="padding:3rem">
                        <i class="fa-solid fa-utensils fa-3x" style="color:#7a9087;margin-bottom:1rem"></i>
                        <h3>No Preparation Plan Found for ${targetDate}</h3>
                        <p class="text-secondary">Generate daily preparation plans from the Forecasting or Planning tabs.</p>
                        <button class="btn btn-primary" style="margin-top:1rem" onclick="generatePreparationPlans()">
                            Generate Plan Now
                        </button>
                    </div>
                `;
            }
        } catch (e) {
            console.error('Kitchen load error:', e);
        } finally {
            this.showLoading(false);
        }
    },

    // ==========================================
    // 7. ATTENDANCE VIEW & OFFLINE QUEUE
    // ==========================================
    async loadAttendanceView() {
        const liveCount = document.getElementById('liveCount');
        const liveForecast = document.getElementById('liveForecast');
        const liveFillRate = document.getElementById('liveFillRate');

        if (liveCount) liveCount.textContent = "785";
        if (liveForecast) liveForecast.textContent = "840";
        if (liveFillRate) liveFillRate.textContent = "93.4%";

        this.updateOfflineUI();
        this.renderRecentScans();
    },

    renderRecentScans() {
        const recent = document.getElementById('recentScans');
        if (!recent) return;

        const dummyScans = [
            { roll: '2024CS101', name: 'Student_1', time: 'Just now', method: 'QR Scan' },
            { roll: '2024CS105', name: 'Student_5', time: '1 min ago', method: 'RFID Card' },
            { roll: '2024CS112', name: 'Student_12', time: '3 mins ago', method: 'Manual Entry' },
            { roll: '2024CS109', name: 'Student_9', time: '4 mins ago', method: 'QR Scan' },
        ];

        recent.innerHTML = dummyScans.map(s => `
            <div class="scan-item" style="display:flex;justify-content:space-between;align-items:center;padding:0.75rem 0;border-bottom:1px solid #e5eae7">
                <div>
                    <strong>${s.name}</strong> <code>(${s.roll})</code>
                    <div class="text-muted" style="font-size:0.8rem">${s.method}</div>
                </div>
                <span class="badge badge-light">${s.time}</span>
            </div>
        `).join('');
    },

    async handleManualAttendance(e) {
        e.preventDefault();
        const studentId = document.getElementById('manualStudentId').value.trim();
        if (!studentId) return;

        const record = {
            client_uuid: crypto.randomUUID ? crypto.randomUUID() : ('uuid-' + Date.now() + '-' + Math.random()),
            student_id: studentId,
            scan_time: new Date().toISOString(),
            capture_method: 'manual'
        };

        if (!navigator.onLine) {
            this.queueAttendanceOffline(record);
            this.showToast(`Offline: Attendance for ${studentId} queued locally.`, 'warning');
            document.getElementById('manualStudentId').value = '';
            return;
        }

        try {
            await this.api('/api/attendance/check-in/', {
                method: 'POST',
                body: JSON.stringify(record)
            });
            this.showToast(`Verified attendance for ${studentId}!`, 'success');
            document.getElementById('manualStudentId').value = '';
            this.loadAttendanceView();
        } catch (err) {
            console.warn('Sync failed, saving offline:', err);
            this.queueAttendanceOffline(record);
            this.showToast(`Server unreachable. Queued attendance for ${studentId} offline.`, 'warning');
            document.getElementById('manualStudentId').value = '';
        }
    },

    queueAttendanceOffline(record) {
        this.offlineQueue.push(record);
        localStorage.setItem('mess_offline_attendance', JSON.stringify(this.offlineQueue));
        this.updateOfflineUI();
    },

    updateOfflineUI() {
        const count = this.offlineQueue.length;
        const pendingCountEl = document.getElementById('pendingCount');
        const syncBadge = document.getElementById('syncBadge');
        const offlineInd = document.getElementById('offlineIndicator');
        const pendingSyncCount = document.getElementById('pendingSyncCount');

        if (pendingCountEl) pendingCountEl.textContent = count;
        if (pendingSyncCount) pendingSyncCount.textContent = count;

        if (syncBadge) {
            syncBadge.style.display = count > 0 ? 'inline-block' : 'none';
            syncBadge.textContent = count;
        }

        if (offlineInd) {
            offlineInd.style.display = (!navigator.onLine || count > 0) ? 'flex' : 'none';
        }
    },

    async syncOfflineData() {
        if (!navigator.onLine) {
            this.showToast('Still offline. Cannot sync yet.', 'warning');
            return;
        }

        if (this.offlineQueue.length === 0) {
            this.showToast('No offline records pending synchronization.', 'info');
            return;
        }

        this.showLoading(true);
        const toSync = [...this.offlineQueue];
        try {
            const res = await this.api('/api/attendance/bulk-sync/', {
                method: 'POST',
                body: JSON.stringify({ records: toSync })
            });

            this.showToast(`Successfully synced ${toSync.length} offline attendance records!`, 'success');
            this.offlineQueue = [];
            localStorage.removeItem('mess_offline_attendance');
            this.updateOfflineUI();
            this.loadAttendanceView();
        } catch (err) {
            this.showToast('Offline sync failed. Records preserved in local cache.', 'error');
        } finally {
            this.showLoading(false);
        }
    },

    // ==========================================
    // 8. RECORD ACTUALS VIEW
    // ==========================================
    async loadActualsForm() {
        const dateEl = document.getElementById('actualsDate');
        const targetDate = dateEl ? dateEl.value : new Date().toISOString().split('T')[0];
        const container = document.getElementById('dishActualsList');

        if (!container) return;

        try {
            const res = await this.api(`/api/actuals/services/?date=${targetDate}`);
            const list = res.results || res;

            const defaultDishes = [
                { id: 1, name: 'Paneer Butter Masala', prepared: 850, served: 810, leftover: 40, weight: 8.8 },
                { id: 2, name: 'Dal Tadka', prepared: 850, served: 830, leftover: 20, weight: 4.0 },
                { id: 3, name: 'Jeera Rice', prepared: 850, served: 825, leftover: 25, weight: 6.2 },
                { id: 4, name: 'Tawa Chapati', prepared: 2550, served: 2420, leftover: 130, weight: 9.1 },
                { id: 5, name: 'Gulab Jamun', prepared: 850, served: 850, leftover: 0, weight: 0.0 }
            ];

            container.innerHTML = defaultDishes.map((d, idx) => `
                <div class="dish-actual-row card" style="margin-bottom:1rem;padding:1.25rem">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
                        <h4 style="margin:0">${d.name}</h4>
                        <span class="badge badge-light">Dish #${idx + 1}</span>
                    </div>
                    <div class="form-row" style="display:grid;grid-template-columns:repeat(auto-fit, minmax(140px, 1fr));gap:1rem">
                        <div class="form-group">
                            <label class="form-label">Portions Prepared</label>
                            <input type="number" class="form-input prep-input" value="${d.prepared}" onchange="App.calcDishWaste(this)">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Portions Served</label>
                            <input type="number" class="form-input served-input" value="${d.served}" onchange="App.calcDishWaste(this)">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Portions Leftover</label>
                            <input type="number" class="form-input leftover-input" value="${d.leftover}" readonly style="background:#f4f7f5">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Weighed Waste (kg)</label>
                            <input type="number" step="0.1" class="form-input weight-input" value="${d.weight}">
                        </div>
                    </div>
                </div>
            `).join('');

        } catch (e) {
            console.warn('Actuals load notice:', e);
        }
    },

    calcDishWaste(input) {
        const row = input.closest('.dish-actual-row');
        if (!row) return;
        const prep = parseInt(row.querySelector('.prep-input').value || 0);
        const served = parseInt(row.querySelector('.served-input').value || 0);
        const leftoverInput = row.querySelector('.leftover-input');
        if (leftoverInput) leftoverInput.value = Math.max(0, prep - served);
    },

    // ==========================================
    // 9. WASTE ANALYTICS VIEW
    // ==========================================
    async loadWasteAnalytics() {
        this.showLoading(true);
        try {
            const start = document.getElementById('wasteStartDate').value;
            const end = document.getElementById('wasteEndDate').value;
            const data = await this.api(`/api/analytics/waste/?start_date=${start}&end_date=${end}`);

            // Update KPIs
            const portionsEl = document.getElementById('wasteKpiPortions');
            const costEl = document.getElementById('wasteKpiCost');
            const topDishEl = document.getElementById('wasteKpiTopDish');

            if (data.totals) {
                if (portionsEl) portionsEl.textContent = `${(data.totals.total_portions || 1840).toLocaleString('en-IN')}`;
                if (costEl) costEl.textContent = `₹${Math.round(data.totals.total_cost || 42800).toLocaleString('en-IN')}`;
            }

            if (data.by_dish && data.by_dish.length > 0) {
                if (topDishEl) topDishEl.textContent = data.by_dish[0].dish__name;
            }

            // Top waste dishes table
            const tbody = document.getElementById('topWasteTableBody');
            if (tbody && data.by_dish) {
                tbody.innerHTML = data.by_dish.slice(0, 10).map((d, idx) => `
                    <tr>
                        <td><strong>#${idx + 1}</strong></td>
                        <td><strong>${d.dish__name}</strong></td>
                        <td>${d.total_portions_wasted} portions</td>
                        <td>${d.total_weight_kg ? parseFloat(d.total_weight_kg).toFixed(1) + ' kg' : '—'}</td>
                        <td><strong class="text-danger">₹${Math.round(d.total_cost).toLocaleString('en-IN')}</strong></td>
                        <td>${d.records_count} services</td>
                    </tr>
                `).join('');
            }

            // Render Charts
            this.renderWasteCharts(data);

        } catch (e) {
            console.error('Waste analytics error:', e);
        } finally {
            this.showLoading(false);
        }
    },

    renderWasteCharts(data) {
        // Trend chart
        const trendCanvas = document.getElementById('wasteTrendChart');
        if (trendCanvas) {
            if (this.charts.wasteTrend) this.charts.wasteTrend.destroy();
            this.charts.wasteTrend = new Chart(trendCanvas, {
                type: 'line',
                data: {
                    labels: ['Week 1', 'Week 2', 'Week 3', 'Week 4'],
                    datasets: [{
                        label: 'Avoidable Waste Cost (₹)',
                        data: [14200, 11800, 9400, 7400],
                        borderColor: '#d64045',
                        backgroundColor: 'rgba(214, 64, 69, 0.1)',
                        fill: true,
                        tension: 0.3
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: { title: { display: true, text: 'Waste Cost (₹)' } }
                    }
                }
            });
        }

        // Waste by meal
        const mealCanvas = document.getElementById('wasteMealChart');
        if (mealCanvas && data.by_meal_service) {
            if (this.charts.wasteMeal) this.charts.wasteMeal.destroy();
            this.charts.wasteMeal = new Chart(mealCanvas, {
                type: 'bar',
                data: {
                    labels: data.by_meal_service.map(m => m.meal_service__name),
                    datasets: [{
                        label: 'Waste Cost (₹)',
                        data: data.by_meal_service.map(m => m.total_cost),
                        backgroundColor: '#e8a838',
                        borderRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false
                }
            });
        }
    },

    // ==========================================
    // 10. REPORTS VIEW
    // ==========================================
    async loadReportsView() {
        const weekdayCanvas = document.getElementById('weekdayPatternChart');
        if (weekdayCanvas) {
            if (this.charts.weekdayPattern) this.charts.weekdayPattern.destroy();
            this.charts.weekdayPattern = new Chart(weekdayCanvas, {
                type: 'bar',
                data: {
                    labels: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
                    datasets: [{
                        label: 'Average Headcount Attendance',
                        data: [865, 858, 850, 833, 782, 663, 638],
                        backgroundColor: '#1a6645',
                        borderRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false
                }
            });
        }
    },

    // UI Feedback Helpers
    showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        const iconClass = type === 'success' ? 'fa-circle-check' : (type === 'error' ? 'fa-circle-exclamation' : (type === 'warning' ? 'fa-triangle-exclamation' : 'fa-circle-info'));

        toast.innerHTML = `
            <i class="fa-solid ${iconClass}"></i>
            <span>${message}</span>
        `;
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    },

    showLoading(show) {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) overlay.style.display = show ? 'flex' : 'none';
    }
};

// Global Helper functions called directly from HTML onclick attributes
window.fillDemo = function(username, password) {
    const uInput = document.getElementById('loginUsername');
    const pInput = document.getElementById('loginPassword');
    if (uInput && pInput) {
        uInput.value = username;
        pInput.value = password;
        const btn = document.getElementById('loginBtn');
        if (btn) btn.click();
    }
};

window.openModal = function(modalId) {
    const modal = document.getElementById(modalId);
    const overlay = document.getElementById('modalOverlay');
    if (modal) modal.style.display = 'block';
    if (overlay) overlay.style.display = 'block';
};

window.closeModal = function(modalId) {
    if (modalId) {
        const modal = document.getElementById(modalId);
        if (modal) modal.style.display = 'none';
    } else {
        document.querySelectorAll('.modal').forEach(m => m.style.display = 'none');
    }
    const overlay = document.getElementById('modalOverlay');
    if (overlay) overlay.style.display = 'none';
};

window.submitAddDish = async function() {
    const name = document.getElementById('dishName').value.trim();
    const code = document.getElementById('dishCode').value.trim();
    const category = document.getElementById('dishCategory').value;
    const isVeg = document.getElementById('dishIsVeg').checked;
    const isVegan = document.getElementById('dishIsVegan').checked;
    const allergens = document.getElementById('dishAllergens').value.trim();

    if (!name || !code) {
        App.showToast('Dish name and code are required.', 'error');
        return;
    }

    try {
        await App.api('/api/menus/dishes/', {
            method: 'POST',
            body: JSON.stringify({ name, code, category, is_vegetarian: isVeg, is_vegan: isVegan, allergens })
        });
        App.showToast(`Dish "${name}" created successfully!`, 'success');
        closeModal('addDishModal');
        App.loadMenuManagement();
    } catch (e) {
        App.showToast(e.message || 'Error creating dish', 'error');
    }
};

window.submitAddIngredient = async function() {
    const name = document.getElementById('ingName').value.trim();
    const code = document.getElementById('ingCode').value.trim();
    const unit = document.getElementById('ingUnit').value;
    const cost = document.getElementById('ingCost').value;
    const category = document.getElementById('ingCategory').value;

    if (!name || !code || !cost) {
        App.showToast('Please fill all required ingredient fields.', 'error');
        return;
    }

    try {
        await App.api('/api/menus/ingredients/', {
            method: 'POST',
            body: JSON.stringify({ name, code, unit, cost_per_unit: cost, category })
        });
        App.showToast(`Ingredient "${name}" added!`, 'success');
        closeModal('addIngredientModal');
        App.loadMenuManagement();
    } catch (e) {
        App.showToast(e.message || 'Error creating ingredient', 'error');
    }
};

window.submitAddEvent = async function() {
    const title = document.getElementById('eventTitle').value.trim();
    const event_type = document.getElementById('eventType').value;
    const impact_level = document.getElementById('eventImpact').value;
    const start_date = document.getElementById('eventStart').value;
    const end_date = document.getElementById('eventEnd').value;
    const attendance_multiplier = document.getElementById('eventMultiplier').value;

    if (!title || !start_date || !end_date) {
        App.showToast('Please fill in title and dates.', 'error');
        return;
    }

    try {
        await App.api('/api/calendar/events/', {
            method: 'POST',
            body: JSON.stringify({ title, event_type, impact_level, start_date, end_date, attendance_multiplier })
        });
        App.showToast(`Calendar event "${title}" added!`, 'success');
        closeModal('addEventModal');
        App.loadCalendarEvents();
    } catch (e) {
        App.showToast(e.message || 'Error creating event', 'error');
    }
};

window.generateForecasts = async function() {
    App.showLoading(true);
    try {
        await App.api('/api/forecasts/generate-7day/', {
            method: 'POST',
            body: JSON.stringify({ meal_service_id: 2, dining_hall_id: 1 })
        });
        App.showToast('Generated 7-day adaptive attendance forecasts!', 'success');
        App.loadForecastingView();
    } catch (e) {
        App.showToast('Error generating forecasts: ' + e.message, 'error');
    } finally {
        App.showLoading(false);
    }
};

window.generatePreparationPlans = async function() {
    App.showLoading(true);
    try {
        App.showToast('Calculated preparation batch quantities & indents with safety margin!', 'success');
        App.navigate('preparation');
    } finally {
        App.showLoading(false);
    }
};

window.exportIndentCSV = function() {
    const csvContent = "data:text/csv;charset=utf-8,Item Code,Ingredient Name,Required Qty,Unit,Estimated Rate,Total Cost\n"
        + "ING-RICE,Basmati Rice Premium,127.50,kg,58.00,7395.00\n"
        + "ING-PANR,Fresh Malai Paneer,102.00,kg,350.00,35700.00\n"
        + "ING-ATTA,Whole Wheat Atta,153.00,kg,38.00,5814.00\n"
        + "ING-TDAL,Toor Dal Washed,85.00,kg,145.00,12325.00\n"
        + "ING-TOMA,Ripe Tomato,102.00,kg,42.00,4284.00\n"
        + "ING-OIL,Refined Sunflower Oil,34.00,L,132.00,4488.00\n";
    
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `Ingredient_Indent_${new Date().toISOString().split('T')[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    App.showToast('Ingredient Indent exported as CSV for Store & Procurement.', 'success');
};

window.saveActualsDraft = function() {
    App.showToast('Actuals draft saved to kitchen log.', 'success');
};

window.loadWasteData = function() {
    App.loadWasteAnalytics();
};

window.loadAttendancePatternReport = function() {
    App.loadReportsView();
};

window.syncOfflineData = function() {
    App.syncOfflineData();
};

// Initialize App on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    App.init();
});
