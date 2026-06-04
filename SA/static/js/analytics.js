document.addEventListener('DOMContentLoaded', function () {
    // --- Chart Default Config ---
    Chart.defaults.color = 'rgba(224, 224, 224, 0.8)';
    Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.1)';

    // --- Fetch Analytics Data ---
    fetch('/api/analytics_data')
        .then(response => response.json())
        .then(data => {
            renderSubjectDistributionChart(data.subject_distribution);
            renderProductivityTrendChart(data.productivity_trend);
        })
        .catch(error => {
            console.error('Error fetching analytics data:', error);
            // You could display an error message on the page here
        });

    // --- Render Donut Chart for Subject Distribution ---
    function renderSubjectDistributionChart(subjectData) {
        const ctx = document.getElementById('subjectDistributionChart')?.getContext('2d');
        if (!ctx) return;

        const labels = subjectData.map(d => d.subject);
        const hours = subjectData.map(d => d.hours);

        const chartColors = [
            '#00c6ff', '#0072ff', '#ff4b2b', '#ffc107', 
            '#28a745', '#9c27b0', '#e91e63', '#607d8b'
        ];

        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Hours Spent',
                    data: hours,
                    backgroundColor: chartColors,
                    borderColor: '#162235',
                    borderWidth: 4,
                    hoverOffset: 10
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            padding: 20,
                            font: {
                                size: 14
                            }
                        }
                    },
                    title: {
                        display: false
                    }
                },
                cutout: '70%'
            }
        });
    }

    // --- Render Line Chart for Productivity Trend ---
    function renderProductivityTrendChart(productivityData) {
        const ctx = document.getElementById('productivityTrendChart')?.getContext('2d');
        if (!ctx) return;

        const sortedData = productivityData.sort((a, b) => new Date(a.date) - new Date(b.date));

        const labels = sortedData.map(d => new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
        const hours = sortedData.map(d => d.hours);

        new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Hours Studied',
                    data: hours,
                    fill: true,
                    backgroundColor: 'rgba(0, 198, 255, 0.2)',
                    borderColor: '#00c6ff',
                    tension: 0.4,
                    pointBackgroundColor: '#00c6ff',
                    pointBorderColor: '#fff',
                    pointHoverRadius: 7,
                    pointRadius: 5
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Hours'
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.05)'
                        }
                    },
                    x: {
                         grid: {
                            display: false
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    }
});