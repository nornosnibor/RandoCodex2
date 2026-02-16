/*
 * AI Usage Dashboard — Frontend JavaScript
 *
 * Fetches data from /api/v1/ endpoints and updates the DOM.
 * Uses Chart.js for the spending trend chart.
 *
 * NOTE: All API calls go to relative URLs (/api/v1/...) so this works
 * whether you access from localhost or another device on the network.
 * A future iOS app would call the same endpoints using the full URL.
 */

// ---- State ----
let spendingChart = null;  // Chart.js instance
let chartDays = 30;        // Default chart range

// ---- Initialization ----
document.addEventListener("DOMContentLoaded", () => {
    loadDashboard();

    // Set up button handlers
    document.getElementById("refresh-btn").addEventListener("click", refreshData);
    document.getElementById("test-btn").addEventListener("click", testConnections);

    // Chart range buttons
    document.querySelectorAll(".chart-range-btn").forEach(btn => {
        btn.addEventListener("click", (e) => {
            chartDays = parseInt(e.target.dataset.days);
            // Update active button style
            document.querySelectorAll(".chart-range-btn").forEach(b => b.classList.remove("active"));
            e.target.classList.add("active");
            loadChart();
        });
    });
});

// ---- Load everything ----
async function loadDashboard() {
    await Promise.all([
        loadSummary(),
        loadChart(),
        loadUsageTable(),
        loadAlerts(),
    ]);
}

// ---- Summary Cards ----
async function loadSummary() {
    try {
        const response = await fetch("/api/v1/summary");
        const data = await response.json();

        // Update total card
        document.getElementById("total-cost").textContent = formatCurrency(data.totals.cost_usd);
        document.getElementById("total-tokens").textContent = formatNumber(data.totals.total_tokens);
        document.getElementById("current-month").textContent = formatMonth(data.month);

        // Update alert badge in header
        updateAlertBadge(data.alerts.status, data.alerts.current_spend);

        // Build provider cards
        const container = document.getElementById("provider-cards");
        container.innerHTML = "";

        for (const provider of data.providers) {
            container.innerHTML += `
                <div class="card card-${provider.provider}">
                    <div class="card-label">${capitalise(provider.provider)}</div>
                    <div class="card-value">${formatCurrency(provider.total_cost || 0)}</div>
                    <div class="card-sub">
                        ${formatNumber(provider.total_tokens || 0)} tokens
                    </div>
                </div>
            `;
        }

        // If no providers have data yet, show a hint
        if (data.providers.length === 0) {
            container.innerHTML = `
                <div class="card">
                    <div class="card-label">No data yet</div>
                    <div class="card-sub">
                        Click "Refresh Data" to fetch usage from your providers,
                        or check that your API keys are configured in .env
                    </div>
                </div>
            `;
        }
    } catch (err) {
        console.error("Failed to load summary:", err);
    }
}

// ---- Spending Trend Chart ----
async function loadChart() {
    try {
        const response = await fetch(`/api/v1/daily?days=${chartDays}`);
        const data = await response.json();

        const labels = data.data.map(d => formatDate(d.date));
        const costs = data.data.map(d => d.total_cost || 0);

        const ctx = document.getElementById("spending-chart").getContext("2d");

        // Destroy previous chart if it exists
        if (spendingChart) {
            spendingChart.destroy();
        }

        spendingChart = new Chart(ctx, {
            type: "bar",
            data: {
                labels: labels,
                datasets: [{
                    label: "Daily Spend ($)",
                    data: costs,
                    backgroundColor: "rgba(99, 102, 241, 0.5)",
                    borderColor: "rgba(99, 102, 241, 1)",
                    borderWidth: 1,
                    borderRadius: 4,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `$${ctx.parsed.y.toFixed(4)}`,
                        },
                    },
                },
                scales: {
                    x: {
                        grid: { color: "rgba(42, 46, 58, 0.5)" },
                        ticks: { color: "#9ca3af", maxRotation: 45 },
                    },
                    y: {
                        grid: { color: "rgba(42, 46, 58, 0.5)" },
                        ticks: {
                            color: "#9ca3af",
                            callback: (value) => `$${value.toFixed(2)}`,
                        },
                        beginAtZero: true,
                    },
                },
            },
        });
    } catch (err) {
        console.error("Failed to load chart:", err);
    }
}

// ---- Usage Table ----
async function loadUsageTable() {
    try {
        const response = await fetch("/api/v1/usage");
        const data = await response.json();

        const tbody = document.getElementById("usage-tbody");
        tbody.innerHTML = "";

        if (data.records.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" style="text-align:center;color:var(--text-muted)">
                        No usage records yet. Click "Refresh Data" to fetch.
                    </td>
                </tr>
            `;
            return;
        }

        // Show most recent records first
        const records = data.records.slice().reverse();

        for (const record of records) {
            tbody.innerHTML += `
                <tr>
                    <td>${formatDate(record.date)}</td>
                    <td>${capitalise(record.provider)}</td>
                    <td class="text-right">${formatNumber(record.input_tokens)}</td>
                    <td class="text-right">${formatNumber(record.output_tokens)}</td>
                    <td class="text-right">${formatNumber(record.total_tokens)}</td>
                    <td class="text-right">${formatCurrency(record.cost_usd)}</td>
                </tr>
            `;
        }
    } catch (err) {
        console.error("Failed to load usage table:", err);
    }
}

// ---- Alerts ----
async function loadAlerts() {
    try {
        const response = await fetch("/api/v1/alerts");
        const data = await response.json();

        const banner = document.getElementById("alert-banner");

        if (data.alerts.length === 0) {
            banner.classList.remove("visible");
            return;
        }

        // Show the most severe alert
        const alert = data.alerts[0];
        banner.className = `alert-banner visible ${alert.alert_type}`;
        document.getElementById("alert-text").textContent =
            `${alert.alert_type === "critical" ? "CRITICAL" : "WARNING"}: ` +
            `Monthly spending ($${alert.amount_usd.toFixed(2)}) has exceeded ` +
            `the $${alert.threshold_usd.toFixed(2)} threshold.`;

        // Set up dismiss button
        document.getElementById("alert-dismiss").onclick = async () => {
            await fetch(`/api/v1/alerts/${alert.id}/acknowledge`, { method: "POST" });
            loadAlerts();
        };
    } catch (err) {
        console.error("Failed to load alerts:", err);
    }
}

// ---- Refresh Data (manual fetch) ----
async function refreshData() {
    const btn = document.getElementById("refresh-btn");
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Fetching...';

    try {
        const response = await fetch("/api/v1/fetch", { method: "POST" });
        const data = await response.json();

        // Show results briefly
        let msg = "Fetch complete: ";
        for (const [provider, result] of Object.entries(data.results)) {
            if (result.success) {
                msg += `${provider} (${result.records_updated} days updated) `;
            } else {
                msg += `${provider} (error: ${result.error}) `;
            }
        }

        btn.textContent = msg;
        setTimeout(() => { btn.textContent = "Refresh Data"; }, 4000);

        // Reload all dashboard data
        await loadDashboard();
    } catch (err) {
        btn.textContent = "Fetch failed - check console";
        setTimeout(() => { btn.textContent = "Refresh Data"; }, 4000);
        console.error("Refresh failed:", err);
    } finally {
        btn.disabled = false;
    }
}

// ---- Test Connections ----
async function testConnections() {
    const btn = document.getElementById("test-btn");
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Testing...';

    const statusContainer = document.getElementById("connection-status");

    try {
        const response = await fetch("/api/v1/test-connection", { method: "POST" });
        const data = await response.json();

        statusContainer.innerHTML = "";

        for (const [provider, result] of Object.entries(data.results)) {
            const dotClass = result.success ? "connected" : "disconnected";
            statusContainer.innerHTML += `
                <div class="status-item">
                    <span>
                        <span class="status-dot ${dotClass}"></span>
                        ${capitalise(provider)}
                    </span>
                    <span style="color: var(--text-muted); font-size: 0.85rem;">
                        ${result.message}
                    </span>
                </div>
            `;
        }

        if (Object.keys(data.results).length === 0) {
            statusContainer.innerHTML = `
                <div class="status-item">
                    <span style="color: var(--text-muted)">
                        No providers configured. Add API keys to your .env file.
                    </span>
                </div>
            `;
        }
    } catch (err) {
        console.error("Test failed:", err);
        statusContainer.innerHTML = `
            <div class="status-item">
                <span style="color: var(--red)">Connection test failed: ${err.message}</span>
            </div>
        `;
    } finally {
        btn.disabled = false;
        btn.textContent = "Test Connections";
    }
}

// ---- Alert Badge ----
function updateAlertBadge(status, amount) {
    const badge = document.getElementById("alert-badge");
    badge.className = `badge badge-${status}`;
    if (status === "ok") {
        badge.textContent = `$${amount.toFixed(2)} this month`;
    } else {
        badge.textContent = `${status.toUpperCase()}: $${amount.toFixed(2)}`;
    }
}

// ---- Formatting Helpers ----
function formatCurrency(amount) {
    if (amount === null || amount === undefined) return "$0.00";
    // Show 4 decimal places for small amounts, 2 for larger
    if (amount > 0 && amount < 0.01) {
        return `$${amount.toFixed(4)}`;
    }
    return `$${amount.toFixed(2)}`;
}

function formatNumber(num) {
    if (num === null || num === undefined) return "0";
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toLocaleString();
}

function formatDate(dateStr) {
    // 'YYYY-MM-DD' -> 'Jan 15'
    const parts = dateStr.split("-");
    const d = new Date(parts[0], parts[1] - 1, parts[2]);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatMonth(monthStr) {
    // 'YYYY-MM' -> 'January 2025'
    const [year, month] = monthStr.split("-");
    const d = new Date(year, month - 1, 1);
    return d.toLocaleDateString("en-US", { month: "long", year: "numeric" });
}

function capitalise(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
}
