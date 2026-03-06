/**
 * AirAware – Chart.js helper functions
 * Used by dashboard.html for forecast and overview charts.
 */

const CHART_DEFAULTS = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { intersect: false, mode: 'index' },
    plugins: {
        legend: { labels: { color: '#8899a6', font: { size: 12 } } },
        tooltip: {
            backgroundColor: '#1a2732',
            titleColor: '#e8edf2',
            bodyColor: '#8899a6',
            borderColor: '#2c3e50',
            borderWidth: 1,
            cornerRadius: 8,
        }
    },
    scales: {
        x: {
            ticks: { color: '#8899a6', maxTicksLimit: 10 },
            grid: { color: 'rgba(44,62,80,0.5)' },
        },
        y: {
            ticks: { color: '#8899a6' },
            grid: { color: 'rgba(44,62,80,0.5)' },
        }
    }
};

/**
 * Create the 48-hour forecast chart on the dashboard.
 */
function createForecastChart(canvasId, hourlyData) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    const labels = hourlyData.map(d => `+${d.hours_ahead}h`);
    const values = hourlyData.map(d => d.predicted_aqi);

    // Color each point based on AQI category
    const colors = values.map(v => {
        if (v <= 50) return '#2ecc71';
        if (v <= 100) return '#f1c40f';
        if (v <= 200) return '#e67e22';
        if (v <= 300) return '#e74c3c';
        return '#8e44ad';
    });

    return new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: 'Predicted AQI',
                data: values,
                borderColor: '#1da1f2',
                backgroundColor: function(context) {
                    const chart = context.chart;
                    const { ctx: c, chartArea } = chart;
                    if (!chartArea) return 'rgba(29,161,242,0.1)';
                    const gradient = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
                    gradient.addColorStop(0, 'rgba(29,161,242,0.3)');
                    gradient.addColorStop(1, 'rgba(29,161,242,0.02)');
                    return gradient;
                },
                fill: true,
                tension: 0.4,
                pointBackgroundColor: colors,
                pointBorderColor: colors,
                pointRadius: 5,
                pointHoverRadius: 7,
            }]
        },
        options: {
            ...CHART_DEFAULTS,
            scales: {
                ...CHART_DEFAULTS.scales,
                y: {
                    ...CHART_DEFAULTS.scales.y,
                    title: { display: true, text: 'AQI', color: '#8899a6' },
                    suggestedMin: 0,
                }
            },
            plugins: {
                ...CHART_DEFAULTS.plugins,
                annotation: {
                    annotations: {
                        goodLine: {
                            type: 'line', yMin: 50, yMax: 50,
                            borderColor: '#2ecc71', borderWidth: 1, borderDash: [5, 5],
                        },
                        moderateLine: {
                            type: 'line', yMin: 100, yMax: 100,
                            borderColor: '#f1c40f', borderWidth: 1, borderDash: [5, 5],
                        },
                        unhealthyLine: {
                            type: 'line', yMin: 200, yMax: 200,
                            borderColor: '#e67e22', borderWidth: 1, borderDash: [5, 5],
                        },
                    }
                }
            }
        }
    });
}

/**
 * Create the 30-day pollution overview chart on the dashboard.
 */
function createOverviewChart(canvasId, trendsData) {
    const ctx = document.getElementById(canvasId).getContext('2d');

    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: trendsData.dates,
            datasets: [
                {
                    label: 'AQI',
                    data: trendsData.aqi,
                    borderColor: '#1da1f2',
                    borderWidth: 2,
                    tension: 0.3,
                    pointRadius: 0,
                },
                {
                    label: 'PM2.5',
                    data: trendsData.pm25,
                    borderColor: '#e74c3c',
                    borderWidth: 2,
                    tension: 0.3,
                    pointRadius: 0,
                },
                {
                    label: 'PM10',
                    data: trendsData.pm10,
                    borderColor: '#e67e22',
                    borderWidth: 2,
                    tension: 0.3,
                    pointRadius: 0,
                },
                {
                    label: 'NO₂',
                    data: trendsData.no2,
                    borderColor: '#9b59b6',
                    borderWidth: 1.5,
                    tension: 0.3,
                    pointRadius: 0,
                    hidden: true,
                },
                {
                    label: 'SO₂',
                    data: trendsData.so2,
                    borderColor: '#f39c12',
                    borderWidth: 1.5,
                    tension: 0.3,
                    pointRadius: 0,
                    hidden: true,
                },
            ]
        },
        options: {
            ...CHART_DEFAULTS,
            scales: {
                ...CHART_DEFAULTS.scales,
                y: {
                    ...CHART_DEFAULTS.scales.y,
                    title: { display: true, text: 'Value', color: '#8899a6' },
                    suggestedMin: 0,
                }
            }
        }
    });
}
