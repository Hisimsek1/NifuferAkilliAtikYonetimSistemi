// Admin Dashboard JavaScript

// XSS koruması için yardımcı fonksiyon
function escapeHtml(str) {
    if (typeof str !== 'string') return String(str);
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// ============== TAB NAVIGATION ==============
function showTab(tabName, evt) {
    // Hide all tabs
    const tabs = document.querySelectorAll('.tab-content');
    tabs.forEach(tab => tab.style.display = 'none');

    // Remove active class from all tab buttons
    const tabButtons = document.querySelectorAll('.admin-tab');
    tabButtons.forEach(btn => btn.classList.remove('active'));

    // Show selected tab
    document.getElementById(`${tabName}-tab`).style.display = 'block';

    // Add active class to clicked button
    const clickedBtn = evt && evt.target ? evt.target : document.querySelector(`[onclick*="${tabName}"]`);
    if (clickedBtn) clickedBtn.classList.add('active');
}

// ============== FLEET CHANGE CALCULATIONS ==============
document.addEventListener('DOMContentLoaded', function() {
    const fleetInputs = [
        { input: 'smallTruckChange', current: 5, total: 'smallTruckTotal' },
        { input: 'largeTruckChange', current: 10, total: 'largeTruckTotal' },
        { input: 'compactorChange', current: 3, total: 'compactorTotal' }
    ];
    
    fleetInputs.forEach(fleet => {
        const input = document.getElementById(fleet.input);
        const totalElement = document.getElementById(fleet.total);
        
        if (input && totalElement) {
            input.addEventListener('input', function() {
                const change = parseInt(this.value) || 0;
                const newTotal = fleet.current + change;
                totalElement.textContent = newTotal;
                
                // Highlight if changed
                if (change !== 0) {
                    totalElement.style.fontWeight = '700';
                    totalElement.style.color = change > 0 ? '#00A651' : '#E74C3C';
                } else {
                    totalElement.style.fontWeight = 'normal';
                    totalElement.style.color = 'inherit';
                }
            });
        }
    });
});

// ============== SIMULATION ENGINE ==============
function runSimulation() {
    const button = document.querySelector('.run-simulation-btn');
    const resultsPanel = document.getElementById('resultsPanel');
    
    // Get input values
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;
    const simName = document.getElementById('simName').value || 'Adsız Simülasyon';
    
    const fleetChanges = {
        small_trucks: parseInt(document.getElementById('smallTruckChange').value) || 0,
        large_trucks: parseInt(document.getElementById('largeTruckChange').value) || 0,
        compactors: parseInt(document.getElementById('compactorChange').value) || 0
    };
    
    const parameters = {
        fuel_price: parseFloat(document.getElementById('fuelPrice').value) || 35.00,
        max_route_duration: parseInt(document.getElementById('maxRouteDuration').value) || 8,
        collection_strategy: document.getElementById('collectionStrategy').value
    };
    
    // Validate
    if (!startDate || !endDate) {
        alert('Lütfen başlangıç ve bitiş tarihlerini seçiniz.');
        return;
    }
    
    // Show loading state
    button.disabled = true;
    button.textContent = 'Simülasyon Çalıştırılıyor...';
    resultsPanel.classList.remove('visible');
    
    // Simulate processing delay
    setTimeout(() => {
        // Calculate simulation results
        const results = calculateSimulation(fleetChanges, parameters);
        
        // Display results
        displayResults(results);
        
        // Reset button
        button.disabled = false;
        button.textContent = 'Simülasyonu Çalıştır';
        
        // Show results panel
        resultsPanel.classList.add('visible');
        
        // Scroll to results
        resultsPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        
    }, 2000); // 2 second delay
}

// ============== SIMULATION CALCULATIONS ==============
function calculateSimulation(fleetChanges, parameters) {
    // Baseline metrics (from historical data)
    const baseline = {
        km_driven: 5400,
        fuel_consumed: 1350,
        co2_emissions: 3510,
        cost: 285000,
        collection_rate: 100,
        satisfaction: 95,
        routes: 180,
        tonnage: 2700000
    };
    
    // Calculate total fleet change
    const totalChange = fleetChanges.small_trucks + fleetChanges.large_trucks + fleetChanges.compactors;
    
    // Route duration effect: default is 8 hours
    // Longer routes = vehicles on road longer = more fuel/km
    // Shorter routes = vehicles on road less = less fuel/km
    const maxRouteDuration = parameters.max_route_duration || 8;
    const route_duration_factor = maxRouteDuration / 8; // 8 is baseline
    
    // Simulation factors (simplified model)
    const efficiency_factor = (1 - (totalChange * 0.05)) * route_duration_factor; // More vehicles = more efficiency
    const vehicle_cost_factor = 1 + (totalChange * 0.03); // Vehicle operating cost
    
    // Calculate simulated metrics
    const simulated = {
        km_driven: Math.round(baseline.km_driven * efficiency_factor),
        fuel_consumed: Math.round(baseline.fuel_consumed * efficiency_factor),
        co2_emissions: Math.round(baseline.co2_emissions * efficiency_factor),
        cost: 0, // Will be calculated below
        collection_rate: Math.max(95, 100 - Math.abs(totalChange * 0.1)), // Only affected by fleet changes
        satisfaction: Math.round(baseline.satisfaction - Math.abs(totalChange * 1.5)),
        routes: Math.round(baseline.routes * route_duration_factor),
        tonnage: Math.round(baseline.tonnage * route_duration_factor + (totalChange * 5000)) // More hours = more waste, more vehicles = more waste
    };
    
    // Calculate cost based on fuel price parameter
    // Cost = (Fuel consumed * Fuel price) + (Vehicle maintenance & personnel)
    const fuelPrice = parameters.fuel_price || 40.74;
    const fuelCost = simulated.fuel_consumed * fuelPrice;
    const vehicleMaintenanceCost = 150000 * vehicle_cost_factor; // Base maintenance cost
    const personnelCost = 80000 * vehicle_cost_factor; // Personnel cost based on fleet size
    
    simulated.cost = Math.round(fuelCost + vehicleMaintenanceCost + personnelCost);
    
    // Calculate changes
    const changes = {
        km: simulated.km_driven - baseline.km_driven,
        fuel: simulated.fuel_consumed - baseline.fuel_consumed,
        co2: simulated.co2_emissions - baseline.co2_emissions,
        cost: simulated.cost - baseline.cost,
        collection_rate: simulated.collection_rate - baseline.collection_rate,
        satisfaction: simulated.satisfaction - baseline.satisfaction,
        routes: simulated.routes - baseline.routes,
        tonnage: simulated.tonnage - baseline.tonnage
    };
    
    // Calculate percentages
    const percentages = {
        km: ((changes.km / baseline.km_driven) * 100).toFixed(1),
        fuel: ((changes.fuel / baseline.fuel_consumed) * 100).toFixed(1),
        co2: ((changes.co2 / baseline.co2_emissions) * 100).toFixed(1),
        cost: ((changes.cost / baseline.cost) * 100).toFixed(1),
        collection_rate: (changes.collection_rate).toFixed(1),
        routes: ((changes.routes / baseline.routes) * 100).toFixed(1),
        tonnage: ((changes.tonnage / baseline.tonnage) * 100).toFixed(1)
    };
    
    // Generate recommendation
    const recommendation = generateRecommendation(changes, totalChange);
    
    return {
        baseline,
        simulated,
        changes,
        percentages,
        recommendation,
        fleetChanges
    };
}

// ============== RECOMMENDATION ENGINE ==============
function generateRecommendation(changes, totalChange) {
    let score = 0;
    const reasons = [];
    
    // Cost effectiveness
    if (changes.cost < 0) {
        score += 30;
        reasons.push(`Aylık ${Math.abs(changes.cost).toLocaleString('tr-TR')} ₺ tasarruf sağlar`);
    } else {
        score -= 20;
        reasons.push(`Aylık ${Math.abs(changes.cost).toLocaleString('tr-TR')} ₺ ek maliyet getirir`);
    }
    
    // Fuel efficiency
    if (changes.fuel < 0) {
        score += 20;
        reasons.push(`${Math.abs(changes.fuel)} L yakıt tasarrufu`);
    }
    
    // Environmental impact
    if (changes.co2 < 0) {
        score += 15;
        reasons.push(`${Math.abs(changes.co2)} kg CO₂ emisyon azalması`);
    }
    
    // Service quality
    if (changes.collection_rate >= -2) {
        score += 25;
        reasons.push('Hizmet kalitesi korunuyor');
    } else {
        score -= 30;
        reasons.push('Hizmet kalitesinde düşüş');
    }
    
    // Determine recommendation level
    let level, cssClass, action;
    
    if (score >= 50) {
        level = 'ŞIDDETLE TAVSİYE EDİLİR';
        cssClass = 'recommended';
        action = 'Bu filo konfigürasyonunu hemen uygulayın';
    } else if (score >= 25) {
        level = 'TAVSİYE EDİLİR';
        cssClass = 'recommended';
        action = 'Daha fazla analiz sonrası uygulamayı düşünün';
    } else if (score >= 0) {
        level = 'NÖTR';
        cssClass = 'neutral';
        action = 'Marjinal faydalar mevcut. İsteğe bağlı uygulama';
    } else {
        level = 'TAVSİYE EDİLMEZ';
        cssClass = 'not-recommended';
        action = 'Uygulamayın. Mevcut filo daha iyi performans gösteriyor';
    }
    
    return {
        level,
        cssClass,
        action,
        score,
        reasons
    };
}

// ============== DISPLAY RESULTS ==============
function displayResults(results) {
    const { baseline, simulated, changes, percentages, recommendation } = results;
    
    // Update recommendation box
    const recBox = document.getElementById('recommendationBox');
    recBox.className = `recommendation-box ${recommendation.cssClass}`;
    
    document.getElementById('recommendationTitle').textContent = 
        `📊 TAVSİYE: ${recommendation.level}`;
    document.getElementById('recommendationText').textContent = 
        recommendation.action;
    
    // Update reasons list
    const reasonsList = document.getElementById('recommendationReasons');
    reasonsList.innerHTML = recommendation.reasons
        .map(reason => `<li>${escapeHtml(reason)}</li>`)
        .join('');
    
    // Update metric cards
    updateMetricCard('km', simulated.km_driven, changes.km, percentages.km);
    updateMetricCard('fuel', simulated.fuel_consumed, changes.fuel, percentages.fuel, 'L');
    updateMetricCard('co2', simulated.co2_emissions, changes.co2, percentages.co2, 'kg');
    updateMetricCard('cost', simulated.cost, changes.cost, percentages.cost, '₺');
    updateMetricCard('collectionRate', simulated.collection_rate.toFixed(1), changes.collection_rate, percentages.collection_rate, '%');
    updateMetricCard('satisfaction', simulated.satisfaction, changes.satisfaction, null);
}

function updateMetricCard(prefix, value, change, percentage, unit = '') {
    const valueElement = document.getElementById(`${prefix}Value`);
    const changeElement = document.getElementById(`${prefix}Change`);
    
    if (valueElement) {
        if (unit === '₺' || unit === '') {
            valueElement.textContent = `${value.toLocaleString('tr-TR')} ${unit}`;
        } else if (unit === '%') {
            valueElement.textContent = `${value}${unit}`;
        } else {
            valueElement.textContent = `${value.toLocaleString('tr-TR')} ${unit}`;
        }
    }
    
    if (changeElement) {
        const isPositive = change < 0; // For cost/emissions, negative is good
        changeElement.className = `metric-change ${isPositive ? 'positive' : 'negative'}`;
        
        const sign = change >= 0 ? '+' : '';
        
        if (percentage !== null) {
            if (unit === '%') {
                changeElement.textContent = `${sign}${change.toFixed(1)} puan`;
            } else {
                changeElement.textContent = `${sign}${change.toLocaleString('tr-TR')} ${unit} (${sign}${percentage}%)`;
            }
        } else {
            changeElement.textContent = `${sign}${change} puan`;
        }
    }
}

// ============== EXPORT & SAVE FUNCTIONS ==============
function exportReport() {
    alert('Rapor PDF olarak indiriliyor...\n(Bu özellik geliştirme aşamasındadır)');
    console.log('Export report functionality would generate PDF here');
}

// ============== FLEET ROUTE OPTIMIZATION ==============
let fleetMap = null;
let routeData = null;

function optimizeRoutes(evt) {
    const button = (evt && evt.target) ? evt.target : document.getElementById('optimizeBtn');
    button.disabled = true;
    button.textContent = 'Rotalar Optimize Ediliyor...';
    
    fetch('/api/fleet/optimize-routes')
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                routeData = data;
                displayRouteSummary(data.summary);
                displayRouteMap(data.routes);
                displayRouteDetails(data.routes);
            } else {
                showAdminNotification('Hata: ' + escapeHtml(data.message || 'Bilinmeyen hata'), 'error');
            }
        })
        .catch(err => {
            console.error('Route optimization error:', err);
            showAdminNotification('Rota optimizasyonu sırasında hata oluştu', 'error');
        })
        .finally(() => {
            button.disabled = false;
            button.textContent = 'Rotaları Optimize Et';
        });
}

function displayRouteSummary(summary) {
    document.getElementById('routeSummary').style.display = 'block';
    document.getElementById('summaryVehicles').textContent = summary.total_vehicles;
    document.getElementById('summaryContainers').textContent = summary.assigned_containers;
    document.getElementById('summaryDistance').textContent = summary.total_distance_km + ' km';
    document.getElementById('summaryTime').textContent = summary.total_time_hours + ' saat';
}

function displayRouteMap(routes) {
    const mapContainer = document.getElementById('fleetMapContainer');
    mapContainer.style.display = 'block';
    
    // Harita zaten varsa event listener'ları da temizle
    if (fleetMap) {
        fleetMap.off();
        fleetMap.remove();
        fleetMap = null;
    }
    
    // Yeni harita oluştur
    fleetMap = L.map('fleetMap').setView([40.19, 28.87], 12);
    
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(fleetMap);
    
    // Her araç için farklı renk
    const colors = ['#E74C3C', '#3498DB', '#2ECC71', '#F39C12', '#9B59B6', '#1ABC9C', '#E67E22', '#34495E', '#E91E63', '#FF5722'];
    
    routes.forEach((route, index) => {
        const color = colors[index % colors.length];
        
        // Rota çizgilerini çiz
        if (route.route_points && route.route_points.length > 0) {
            const polyline = L.polyline(route.route_points, {
                color: color,
                weight: 3,
                opacity: 0.7
            }).addTo(fleetMap);
            
            // Her konteynere marker ekle
            route.route_points.forEach((point, idx) => {
                const marker = L.circleMarker(point, {
                    radius: 6,
                    fillColor: color,
                    color: '#fff',
                    weight: 2,
                    opacity: 1,
                    fillOpacity: 0.8
                }).addTo(fleetMap);
                
                marker.bindPopup(`
                    <strong>${route.plate_number}</strong><br>
                    Konteyner #${idx + 1}<br>
                    Tip: ${route.container_details[idx].container_type}
                `);
            });
            
            // İlk noktaya başlangıç marker'ı
            if (route.route_points.length > 0) {
                L.marker(route.route_points[0], {
                    icon: L.divIcon({
                        html: `<div style="background: ${color}; color: white; border-radius: 50%; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; font-weight: bold; border: 2px solid white;">${index + 1}</div>`,
                        className: '',
                        iconSize: [30, 30]
                    })
                }).addTo(fleetMap).bindPopup(`<strong>Başlangıç</strong><br>${route.plate_number}`);
            }
        }
    });
    
    // Haritayı tüm rotaları gösterecek şekilde ayarla
    const allPoints = routes.flatMap(r => r.route_points);
    if (allPoints.length > 0) {
        fleetMap.fitBounds(allPoints);
    }
}

function displayRouteDetails(routes) {
    document.getElementById('routeDetails').style.display = 'block';
    const routeList = document.getElementById('routeList');
    
    const colors = ['#E74C3C', '#3498DB', '#2ECC71', '#F39C12', '#9B59B6', '#1ABC9C', '#E67E22', '#34495E', '#E91E63', '#FF5722'];
    
    routeList.innerHTML = routes.map((route, index) => {
        const color = colors[index % colors.length];
        return `
            <div style="background: white; border-radius: 8px; padding: 1.5rem; margin-bottom: 1rem; border-left: 4px solid ${color}; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                    <h4 style="color: ${color}; margin: 0;">
                        <span style="display: inline-block; width: 30px; height: 30px; background: ${color}; color: white; border-radius: 50%; text-align: center; line-height: 30px; margin-right: 10px;">${index + 1}</span>
                        ${route.plate_number} - ${route.vehicle_type}
                    </h4>
                    <span style="background: ${color}20; color: ${color}; padding: 0.5rem 1rem; border-radius: 20px; font-weight: 600;">
                        ${route.capacity_usage}% Doluluk
                    </span>
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem; margin-top: 1rem;">
                    <div>
                        <div style="font-size: 0.9rem; color: #666;">Konteyner Sayısı</div>
                        <div style="font-size: 1.3rem; font-weight: 600; color: #333;">${route.total_containers}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.9rem; color: #666;">Mesafe</div>
                        <div style="font-size: 1.3rem; font-weight: 600; color: #333;">${route.total_distance_km} km</div>
                    </div>
                    <div>
                        <div style="font-size: 0.9rem; color: #666;">Tahmini Süre</div>
                        <div style="font-size: 1.3rem; font-weight: 600; color: #333;">${route.estimated_time_min} dk</div>
                    </div>
                    <div>
                        <div style="font-size: 0.9rem; color: #666;">Toplam Ağırlık</div>
                        <div style="font-size: 1.3rem; font-weight: 600; color: #333;">${route.total_weight_tons} ton</div>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// ============== NOTIFICATION HELPER ==============
function showAdminNotification(message, type = 'info') {
    let container = document.getElementById('adminNotifContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'adminNotifContainer';
        container.style.cssText = 'position:fixed;top:80px;right:20px;z-index:9999;display:flex;flex-direction:column;gap:8px;max-width:360px;';
        document.body.appendChild(container);
    }

    const colors = { error: '#dc2626', success: '#16a34a', info: '#1e3a5f', warning: '#ca8a04' };
    const icons = { error: '✕', success: '✓', info: 'ℹ', warning: '⚠' };
    const color = colors[type] || colors.info;

    const toast = document.createElement('div');
    toast.style.cssText = `background:#fff;border-left:4px solid ${color};padding:12px 16px;border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,0.15);display:flex;align-items:flex-start;gap:10px;font-family:inherit;font-size:0.875rem;`;
    toast.innerHTML = `<span style="color:${color};font-weight:700;flex-shrink:0;">${icons[type]}</span><span style="flex:1;color:#1e293b;">${escapeHtml(message)}</span><button onclick="this.parentElement.remove()" style="background:none;border:none;color:#94a3b8;cursor:pointer;font-size:1rem;padding:0;flex-shrink:0;">×</button>`;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
}

// ============== INITIALIZATION ==============
console.log('Admin dashboard loaded successfully');
