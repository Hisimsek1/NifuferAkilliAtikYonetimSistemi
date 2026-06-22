"""
Flask Backend - SQLite
Basitleştirilmiş Demo
"""

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
from datetime import datetime
import joblib
import numpy as np
import os
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

app = Flask(__name__, static_folder='public', static_url_path='')
CORS(app)

DB_PATH = 'nilufer_waste.db'
MODEL_PATH = 'models/fill_predictor.pkl'

# Model yükle
model_data = None
try:
    model_data = joblib.load(MODEL_PATH)
    print(f"✓ Model yüklendi")
except (FileNotFoundError, Exception) as e:
    print(f"⚠️ Model bulunamadı: {e}")

# Model eğitim sayacı (her 10 doğru bildirimde bir eğit)
training_counter = {'verified_count': 0, 'threshold': 10}

def retrain_model():
    """Model'i güncel verilerle yeniden eğit"""
    global model_data
    
    try:
        conn = sqlite3.connect(DB_PATH)
        
        # Eğitim verilerini hazırla - hem eski hem yeni veriler
        query = """
        SELECT 
            c.container_id,
            c.container_type,
            c.capacity_liters,
            c.current_fill_level,
            n.population_density,
            CASE 
                WHEN c.current_fill_level >= 0.75 THEN 1 
                ELSE 0 
            END as is_full
        FROM containers c
        LEFT JOIN neighborhoods n ON c.neighborhood_id = n.neighborhood_id
        WHERE c.status = 'active'
        """
        
        df = pd.read_sql_query(query, conn)
        
        if len(df) < 50:  # Minimum veri kontrolü
            conn.close()
            return False
        
        # Feature engineering
        df['type_glass'] = (df['container_type'] == 'Cam').astype(int)
        df['type_paper'] = (df['container_type'] == 'Kağıt').astype(int)
        df['type_plastic'] = (df['container_type'] == 'Plastik').astype(int)
        df['type_metal'] = (df['container_type'] == 'Metal').astype(int)
        df['type_organic'] = (df['container_type'] == 'Organik').astype(int)
        df['type_general'] = (df['container_type'] == 'Genel').astype(int)
        
        df['capacity_large'] = (df['capacity_liters'] >= 1100).astype(int)
        df['capacity_medium'] = ((df['capacity_liters'] >= 800) & (df['capacity_liters'] < 1100)).astype(int)
        df['density_high'] = (df['population_density'] > 10000).astype(int)
        
        # Features ve target
        feature_cols = ['container_id', 'capacity_liters', 'population_density',
                       'type_glass', 'type_paper', 'type_plastic', 'type_metal', 
                       'type_organic', 'type_general', 'capacity_large', 
                       'capacity_medium', 'density_high', 'current_fill_level']
        
        X = df[feature_cols].fillna(0)
        y = df['is_full']
        
        # Train-test split
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        # Model eğit
        model = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=10)
        model.fit(X_train, y_train)
        
        # Accuracy hesapla
        train_accuracy = model.score(X_train, y_train)
        test_accuracy = model.score(X_test, y_test)
        
        # Model'i kaydet
        model_data = {
            'model': model,
            'feature_columns': feature_cols,
            'train_accuracy': train_accuracy,
            'test_accuracy': test_accuracy,
            'trained_at': datetime.now().isoformat()
        }
        
        joblib.dump(model_data, MODEL_PATH)
        conn.close()
        
        print(f"✅ Model yeniden eğitildi! Train: {train_accuracy:.3f}, Test: {test_accuracy:.3f}")
        return True
        
    except Exception as e:
        print(f"❌ Model eğitim hatası: {e}")
        return False

@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

@app.route('/admin')
def admin():
    return send_from_directory('public', 'admin.html')

@app.route('/api/dashboard/stats')
def dashboard_stats():
    """Dashboard istatistikleri"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Toplam konteyner
    cursor.execute("SELECT COUNT(*) FROM containers WHERE status='active'")
    total = cursor.fetchone()[0]
    
    # Dolu konteynerler
    cursor.execute("SELECT COUNT(*) FROM containers WHERE current_fill_level >= 0.75")
    full = cursor.fetchone()[0]
    
    # Toplam araç
    cursor.execute("SELECT COUNT(*) FROM vehicles")
    vehicles = cursor.fetchone()[0]
    
    # Mahalleler
    cursor.execute("SELECT COUNT(*) FROM neighborhoods")
    neighborhoods = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'total_containers': total,
        'full_containers': full,
        'fill_rate': full / total if total > 0 else 0,
        'total_vehicles': vehicles,
        'neighborhoods': neighborhoods,
        'today_reports': 12,
        'today_collections': 45,
        'month_tonnage': 3542.5
    })

@app.route('/api/leaderboard')
def leaderboard():
    """Kullanıcı liderlik tablosu"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT name, trust_score, total_reports
        FROM users
        WHERE role = 'citizen' AND total_reports > 0
        ORDER BY trust_score DESC, total_reports DESC
        LIMIT 10
    """)
    
    users = cursor.fetchall()
    conn.close()
    
    return jsonify({
        'leaderboard': [
            {
                'rank': idx + 1,
                'name': u[0],
                'trust_score': float(u[1]),
                'total_reports': u[2]
            }
            for idx, u in enumerate(users)
        ]
    })

@app.route('/api/predict/<int:container_id>')
def predict_container(container_id):
    """Tek konteyner tahmini"""
    if not model_data:
        return jsonify({'error': 'Model yüklü değil'}), 503
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            c.container_id,
            c.container_type,
            c.capacity_liters,
            c.last_collection_date,
            c.current_fill_level,
            c.latitude,
            c.longitude,
            n.neighborhood_name,
            n.population,
            n.population_density,
            n.area_km2
        FROM containers c
        LEFT JOIN neighborhoods n ON c.neighborhood_id = n.neighborhood_id
        WHERE c.container_id = ?
    """, (container_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return jsonify({'error': 'Konteyner bulunamadı'}), 404
    
    # Özellikleri oluştur
    if row[3]:
        last_date = datetime.fromisoformat(row[3])
        hours_since = (datetime.now() - last_date).total_seconds() / 3600
    else:
        hours_since = 168
    
    days_since = hours_since / 24
    now = datetime.now()
    day_of_week = now.weekday()
    is_weekend = int(now.weekday() >= 5)
    month = now.month
    season = (month % 12) // 3
    
    capacity = row[2]
    container_type_map = {'underground': 4, '770lt': 3, '400lt': 2, 'plastic': 1}
    container_type_encoded = container_type_map.get(row[1], 2)
    
    population = row[8] if row[8] else 10000
    pop_density = row[9] if row[9] else 5000
    area = row[10] if row[10] else 2.0
    
    features = [
        hours_since, days_since, day_of_week, is_weekend, month, season,
        capacity, container_type_encoded, population, pop_density, area,
        0.5, 0.5, 10, 0.5
    ]
    
    # Tahmin
    model = model_data['model']
    probabilities = model.predict_proba([features])[0]
    fill_probability = probabilities[1]
    
    return jsonify({
        'container_id': container_id,
        'neighborhood': row[7],
        'container_type': row[1],
        'capacity_liters': row[2],
        'current_fill_level': float(row[4]),
        'fill_probability': float(fill_probability),
        'is_full': bool(fill_probability >= 0.75),
        'confidence': float(max(probabilities)),
        'latitude': float(row[5]),
        'longitude': float(row[6]),
        'model_version': model_data.get('trained_at', 'unknown'),
        'prediction_timestamp': datetime.now().isoformat()
    })

@app.route('/api/auth/register', methods=['POST'])
def register():
    """Kullanıcı kaydı - TC numarası ile"""
    from flask import request
    from werkzeug.security import generate_password_hash
    
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Geçersiz veya eksik JSON gövdesi'}), 400

    required = ['name', 'tc_number', 'phone', 'password']
    if not all(k in data for k in required):
        return jsonify({'error': 'Tüm alanları doldurun'}), 400

    # Uzunluk sınırları
    if len(str(data['name'])) > 100:
        return jsonify({'error': 'İsim çok uzun'}), 400
    if len(str(data['password'])) < 6:
        return jsonify({'error': 'Şifre en az 6 karakter olmalıdır'}), 400
    if len(str(data['password'])) > 200:
        return jsonify({'error': 'Şifre çok uzun'}), 400
    if len(str(data['phone'])) > 20:
        return jsonify({'error': 'Telefon numarası geçersiz'}), 400

    # TC numarası doğrulama (11 haneli)
    tc = str(data['tc_number']).strip()
    if len(tc) != 11 or not tc.isdigit():
        return jsonify({'error': 'TC numarası 11 haneli olmalıdır'}), 400
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # TC kontrolü
    cursor.execute("SELECT user_id FROM users WHERE tc_number = ?", (tc,))
    if cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Bu TC numarası zaten kayıtlı'}), 400
    
    # Şifre hash
    password_hash = generate_password_hash(data['password'])
    
    # Kullanıcıyı kaydet (email TC numarasından oluşturulur)
    email = f"{tc}@nilufer.local"
    cursor.execute("""
        INSERT INTO users (name, email, tc_number, phone, password_hash, role, trust_score)
        VALUES (?, ?, ?, ?, ?, 'citizen', 0.5)
    """, (data['name'], email, tc, data['phone'], password_hash))
    
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    
    return jsonify({
        'success': True,
        'user_id': user_id,
        'message': 'Kayıt başarılı! Şimdi giriş yapabilirsiniz.'
    })

@app.route('/api/auth/login', methods=['POST'])
def login():
    """Kullanıcı girişi - TC numarası ile"""
    from flask import request
    from werkzeug.security import check_password_hash
    
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Geçersiz veya eksik JSON gövdesi'}), 400

    if not data.get('tc_number') or not data.get('password'):
        return jsonify({'error': 'TC numarası ve şifre gerekli'}), 400
    
    tc = str(data['tc_number']).strip()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT user_id, name, tc_number, password_hash, role, trust_score, total_reports
        FROM users WHERE tc_number = ?
    """, (tc,))
    
    user = cursor.fetchone()
    conn.close()
    
    if not user or not check_password_hash(user[3], data['password']):
        return jsonify({'error': 'TC numarası veya şifre hatalı'}), 401
    
    return jsonify({
        'success': True,
        'user': {
            'id': user[0],
            'name': user[1],
            'tc_number': user[2],
            'role': user[4],
            'trust_score': float(user[5]),
            'total_reports': user[6]
        }
    })

@app.route('/api/containers/full')
def full_containers():
    """Dolu konteynerleri listele"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            c.container_id,
            c.container_type,
            c.current_fill_level,
            c.latitude,
            c.longitude,
            n.neighborhood_name
        FROM containers c
        LEFT JOIN neighborhoods n ON c.neighborhood_id = n.neighborhood_id
        WHERE c.current_fill_level >= 0.75
        ORDER BY c.current_fill_level DESC
        LIMIT 50
    """)
    
    containers = cursor.fetchall()
    conn.close()
    
    return jsonify({
        'count': len(containers),
        'containers': [
            {
                'id': c[0],
                'type': c[1],
                'fill_level': float(c[2]),
                'latitude': float(c[3]),
                'longitude': float(c[4]),
                'neighborhood': c[5]
            }
            for c in containers
        ]
    })

@app.route('/api/containers/all')
def all_containers():
    """Tüm konteynerleri listele"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            c.container_id,
            c.container_type,
            c.current_fill_level,
            c.latitude,
            c.longitude,
            c.capacity_liters,
            c.status,
            n.neighborhood_name
        FROM containers c
        LEFT JOIN neighborhoods n ON c.neighborhood_id = n.neighborhood_id
        WHERE c.status = 'active'
        ORDER BY c.container_id ASC
    """)
    
    containers = cursor.fetchall()
    conn.close()
    
    return jsonify({
        'count': len(containers),
        'containers': [
            {
                'id': c[0],
                'type': c[1],
                'fill_level': float(c[2]),
                'latitude': float(c[3]),
                'longitude': float(c[4]),
                'capacity': c[5],
                'status': c[6],
                'neighborhood': c[7]
            }
            for c in containers
        ]
    })

@app.route('/api/containers/map')
def containers_map():
    """Harita için tüm konteynerlerin lokasyonlarını döndür"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            c.container_id,
            c.container_type,
            c.current_fill_level,
            c.latitude,
            c.longitude,
            c.capacity_liters,
            n.neighborhood_name,
            c.last_collection_date
        FROM containers c
        LEFT JOIN neighborhoods n ON c.neighborhood_id = n.neighborhood_id
        WHERE c.status = 'active' 
        AND c.latitude IS NOT NULL 
        AND c.longitude IS NOT NULL
        ORDER BY c.current_fill_level DESC
    """)
    
    containers = cursor.fetchall()
    conn.close()
    
    return jsonify({
        'count': len(containers),
        'containers': [
            {
                'id': c[0],
                'type': c[1],
                'fill_level': float(c[2]),
                'lat': float(c[3]),
                'lng': float(c[4]),
                'capacity': c[5],
                'neighborhood': c[6],
                'last_collection': c[7]
            }
            for c in containers
        ]
    })

@app.route('/api/reports/submit', methods=['POST'])
def submit_report():
    """Vatandaş bildirimi gönder"""
    from flask import request
    
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Geçersiz veya eksik JSON gövdesi'}), 400

    # Zorunlu alanlar
    if not all(k in data for k in ['user_id', 'container_id', 'fill_level']):
        return jsonify({'error': 'Eksik bilgi'}), 400

    try:
        user_id = int(data['user_id'])
        container_id = int(data['container_id'])
        fill_level = float(data['fill_level']) / 100.0  # Yüzdeyi 0-1 arasına çevir
    except (ValueError, TypeError):
        return jsonify({'error': 'Geçersiz user_id, container_id veya fill_level değeri'}), 400

    if not (0.0 <= fill_level <= 1.0):
        return jsonify({'error': 'fill_level 0 ile 100 arasında olmalıdır'}), 400

    notes = str(data.get('notes', ''))[:500]  # 500 karakter ile sınırla
    has_photo = bool(data.get('has_photo', False))
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Kullanıcı bilgilerini al
    cursor.execute("SELECT trust_score, total_reports FROM users WHERE user_id = ?", (user_id,))
    user_info = cursor.fetchone()
    
    if not user_info:
        conn.close()
        return jsonify({'error': 'Kullanıcı bulunamadı'}), 404
    
    current_trust = user_info[0]
    total_reports = user_info[1] if user_info[1] else 0
    
    # Konteyner mevcut doluluk seviyesini al
    cursor.execute("SELECT current_fill_level FROM containers WHERE container_id = ?", (container_id,))
    container_info = cursor.fetchone()
    
    if not container_info:
        conn.close()
        return jsonify({'error': 'Konteyner bulunamadı'}), 404
    
    actual_fill = container_info[0]
    
    # Doğruluk hesapla (fark ne kadar küçükse o kadar doğru)
    accuracy = 1.0 - abs(fill_level - actual_fill)
    accuracy = max(0.0, min(1.0, accuracy))  # 0-1 arası sınırla
    
    # Güven puanını güncelle
    # Doğru bildirim (+0.05), yanlış bildirim (-0.03)
    if accuracy >= 0.7:  # Doğru bildirim
        trust_change = 0.05
        status = 'verified'
    elif accuracy >= 0.4:  # Orta seviye
        trust_change = 0.01
        status = 'pending'
    else:  # Yanlış bildirim
        trust_change = -0.03
        status = 'rejected'
    
    # Fotoğraf varsa bonus
    if has_photo and current_trust < 0.7:
        trust_change += 0.02
    
    new_trust = current_trust + trust_change
    new_trust = max(0.0, min(1.0, new_trust))  # 0-1 arası sınırla
    
    # Bildirimi kaydet (citizen_reports tablosu kullan)
    cursor.execute("""
        INSERT INTO citizen_reports 
        (user_id, container_id, fill_level_estimate, latitude, longitude, 
         notes, prediction_diff, is_verified, actual_full, submitted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, container_id, fill_level, 40.2, 28.9, 
          notes, abs(fill_level - actual_fill), 
          1 if status == 'verified' else 0, 
          int(actual_fill >= 0.75),
          datetime.now().isoformat()))
    
    # Kullanıcı istatistiklerini güncelle
    cursor.execute("""
        UPDATE users 
        SET trust_score = ?, 
            total_reports = ?,
            accurate_reports = CASE WHEN ? = 'verified' THEN accurate_reports + 1 ELSE accurate_reports END
        WHERE user_id = ?
    """, (new_trust, total_reports + 1, status, user_id))
    
    # Eğer bildirim doğrulanmışsa, konteyner doluluk seviyesini güncelle
    if status == 'verified' and accuracy >= 0.8:  # Çok doğru tahminlerde güncelle
        cursor.execute("""
            UPDATE containers 
            SET current_fill_level = ?,
                last_collection_date = ?
            WHERE container_id = ?
        """, (fill_level, datetime.now().isoformat(), container_id))
        
        # Model eğitim sayacını artır
        training_counter['verified_count'] += 1
        
        # Belirli sayıda doğru bildirimde model'i yeniden eğit
        if training_counter['verified_count'] >= training_counter['threshold']:
            conn.commit()
            conn.close()
            
            # Model'i arka planda eğit
            print(f"🔄 {training_counter['verified_count']} doğru bildirim toplandı, model yeniden eğitiliyor...")
            retrain_success = retrain_model()
            
            if retrain_success:
                training_counter['verified_count'] = 0  # Sayacı sıfırla
            
            return jsonify({
                'success': True,
                'message': 'Bildirim kaydedildi ve model güncellendi!',
                'report_status': status,
                'accuracy': round(accuracy * 100, 1),
                'trust_score': round(new_trust, 2),
                'total_reports': total_reports + 1,
                'trust_change': round(trust_change, 3),
                'model_updated': retrain_success
            })
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'message': 'Bildirim başarıyla kaydedildi!',
        'report_status': status,
        'accuracy': round(accuracy * 100, 1),
        'trust_score': round(new_trust, 2),
        'total_reports': total_reports + 1,
        'trust_change': round(trust_change, 3)
    })

@app.route('/api/simulate', methods=['POST'])
def simulate():
    """Basit simülasyon"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM containers WHERE current_fill_level >= 0.75")
    full_containers = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM vehicles")
    total_vehicles = cursor.fetchone()[0]
    
    conn.close()
    
    # Basit hesaplama
    estimated_hours = (full_containers / (total_vehicles * 8)) if total_vehicles > 0 else 24
    estimated_cost = total_vehicles * 600
    
    return jsonify({
        'success': True,
        'results': {
            'total_vehicles': total_vehicles,
            'estimated_hours': round(estimated_hours, 2),
            'estimated_cost': estimated_cost,
            'containers_to_collect': full_containers,
            'efficiency': min(100, 100 - (estimated_hours / 24 * 100))
        }
    })

# ============== FLEET ROUTE OPTIMIZATION ==============
@app.route('/api/fleet/optimize-routes', methods=['GET'])
def optimize_routes():
    """Her araç için optimize edilmiş rota oluştur"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Aktif araçları getir
        cursor.execute("""
            SELECT v.vehicle_id, v.plate_number, vt.type_name, vt.capacity_tons, vt.hourly_cost
            FROM vehicles v
            JOIN vehicle_types vt ON v.type_id = vt.type_id
            WHERE v.status = 'active'
            ORDER BY v.vehicle_id
        """)
        vehicles = [dict(row) for row in cursor.fetchall()]
        
        # Dolu konteynerleri getir (>%70 dolu olanlar - daha fazla konteyner)
        # Gerçekçi dağılım için: 45 araç × 25 konteyner = ~1100 konteyner hedef
        cursor.execute("""
            SELECT 
                container_id,
                latitude,
                longitude,
                container_type,
                current_fill_level,
                capacity_liters,
                neighborhood_id
            FROM containers
            WHERE status = 'active' 
            AND latitude IS NOT NULL 
            AND longitude IS NOT NULL
            AND current_fill_level >= 0.70
            ORDER BY current_fill_level DESC, neighborhood_id
            LIMIT 1200
        """)
        containers = [dict(row) for row in cursor.fetchall()]
        
        if not vehicles:
            conn.close()
            return jsonify({'success': False, 'message': 'Aktif araç bulunamadı'})
        
        if not containers:
            conn.close()
            return jsonify({'success': False, 'message': 'Toplanacak konteyner bulunamadı'})
        
        # Her araç için rota oluştur (Round-Robin + Geographic Clustering)
        routes = []
        containers_per_vehicle = len(containers) // len(vehicles)
        
        # Mahalleye göre grupla
        neighborhood_groups = {}
        for container in containers:
            nh_id = container['neighborhood_id']
            if nh_id not in neighborhood_groups:
                neighborhood_groups[nh_id] = []
            neighborhood_groups[nh_id].append(container)
        
        # Mahalle gruplarını sırala (en fazla konteynerden aza)
        sorted_neighborhoods = sorted(neighborhood_groups.items(), key=lambda x: len(x[1]), reverse=True)
        
        # Araçlara kapasite kontrolü ile dağıt
        # Gerçekçi dağılım: Maksimum 30 konteyner/araç (çöp arabası kapasitesine göre)
        MAX_CONTAINERS_PER_VEHICLE = 30
        vehicle_assignments = {v['vehicle_id']: {'containers': [], 'weight': 0, 'capacity': v['capacity_tons']} for v in vehicles}
        vehicle_idx = 0
        
        for nh_id, nh_containers in sorted_neighborhoods:
            for container in nh_containers:
                # Konteyner ağırlığını hesapla (ton cinsinden)
                # Gerçek atık yoğunluğu: Organik ~0.4kg/L, Plastik ~0.15kg/L, Cam ~0.6kg/L, Genel ~0.3kg/L
                waste_density = 0.3  # Ortalama genel atık yoğunluğu (kg/L)
                container_weight = (container['capacity_liters'] * container['current_fill_level'] * waste_density) / 1000  # ton cinsinden
                
                # Uygun araç bul (kapasite ve sayı uygun olan)
                attempts = 0
                assigned = False
                while attempts < len(vehicles):
                    target_vehicle = vehicles[vehicle_idx]['vehicle_id']
                    vehicle_data = vehicle_assignments[target_vehicle]
                    
                    # Konteyner sayısı kontrolü + Kapasite kontrolü (%90'a kadar doldur - gerçekçi)
                    if (len(vehicle_data['containers']) < MAX_CONTAINERS_PER_VEHICLE and 
                        vehicle_data['weight'] + container_weight <= vehicle_data['capacity'] * 0.90):
                        vehicle_data['containers'].append(container)
                        vehicle_data['weight'] += container_weight
                        assigned = True
                        break
                    
                    # Bir sonraki araca geç
                    vehicle_idx = (vehicle_idx + 1) % len(vehicles)
                    attempts += 1
                
                # Hiçbir araca sığmıyorsa, en az dolu araca ekle (ama yine limitlere dikkat et)
                if not assigned:
                    available_vehicles = [(vid, vdata) for vid, vdata in vehicle_assignments.items() 
                                        if len(vdata['containers']) < MAX_CONTAINERS_PER_VEHICLE and
                                           vdata['weight'] + container_weight <= vdata['capacity']]
                    
                    if available_vehicles:
                        min_vehicle = min(available_vehicles, key=lambda x: x[1]['weight'])
                        min_vehicle[1]['containers'].append(container)
                        min_vehicle[1]['weight'] += container_weight
                
                vehicle_idx = (vehicle_idx + 1) % len(vehicles)
        
        # Her araç için rota detayları oluştur
        for vehicle in vehicles:
            vehicle_id = vehicle['vehicle_id']
            vehicle_data = vehicle_assignments[vehicle_id]
            assigned_containers = vehicle_data['containers']
            
            if not assigned_containers:
                continue
            
            # COĞRAFİ SIRALAMA: En yakın komşu algoritması (Nearest Neighbor TSP)
            # Başlangıç noktası: İlk konteyner (en dolu olan)
            sorted_containers = [assigned_containers[0]]
            remaining = assigned_containers[1:]
            
            while remaining:
                last_point = sorted_containers[-1]
                # En yakın konteyneri bul
                nearest = min(remaining, key=lambda c: 
                    ((c['latitude'] - last_point['latitude'])**2 + 
                     (c['longitude'] - last_point['longitude'])**2)**0.5
                )
                sorted_containers.append(nearest)
                remaining.remove(nearest)
            
            assigned_containers = sorted_containers
            
            # Mesafe ve süre hesapla (basitleştirilmiş)
            total_distance = len(assigned_containers) * 2.5  # Ortalama 2.5 km per konteyner
            avg_speed = 35  # Ortalama hız km/h (şehir içi)
            total_time = (total_distance / avg_speed) * 60  # dakika
            total_time += len(assigned_containers) * 5  # Her konteyner için 5 dk toplama süresi
            
            # Toplam ağırlık (ton cinsinden) - zaten vehicle_data'da hesaplanmış
            total_weight_tons = vehicle_data['weight']
            capacity_tons = vehicle['capacity_tons']
            
            # Kapasite kullanımını hesapla ve %100 ile sınırla
            if capacity_tons > 0:
                capacity_usage = min(100.0, round((total_weight_tons / capacity_tons) * 100, 1))
            else:
                capacity_usage = 0
            
            # Rota noktaları (lat, lng)
            route_points = [[c['latitude'], c['longitude']] for c in assigned_containers]
            
            routes.append({
                'vehicle_id': vehicle_id,
                'plate_number': vehicle['plate_number'],
                'vehicle_type': vehicle['type_name'],
                'capacity_tons': capacity_tons,
                'total_containers': len(assigned_containers),
                'total_distance_km': round(total_distance, 2),
                'estimated_time_min': round(total_time, 0),
                'total_weight_tons': round(total_weight_tons, 2),
                'capacity_usage': capacity_usage,
                'route_points': route_points,
                'container_details': assigned_containers
            })
        
        # Genel istatistikler
        total_containers = len(containers)
        total_distance = sum(r['total_distance_km'] for r in routes)
        total_time = sum(r['estimated_time_min'] for r in routes)
        
        conn.close()
        
        return jsonify({
            'success': True,
            'summary': {
                'total_vehicles': len(vehicles),
                'total_containers': total_containers,
                'assigned_containers': sum(r['total_containers'] for r in routes),
                'total_distance_km': round(total_distance, 2),
                'total_time_hours': round(total_time / 60, 2),
                'avg_containers_per_vehicle': round(total_containers / len(vehicles), 1)
            },
            'routes': routes
        })
        
    except Exception as e:
        conn.close()
        print(f"optimize_routes hatası: {e}")
        return jsonify({'success': False, 'message': 'Rota optimizasyonu sırasında bir hata oluştu'})

if __name__ == '__main__':
    print("=" * 60)
    print("NİLÜFER BELEDİYESİ - BACKEND API")
    print("=" * 60)
    print(f"\n✓ Model: {'Yüklü ✓' if model_data else 'YÜKLENMEDİ ✗'}")
    print(f"✓ Veritabanı: {DB_PATH}")
    print("\n🌐 URL'ler:")
    print("  Vatandaş: http://localhost:5000/")
    print("  Admin: http://localhost:5000/admin")
    print("\n" + "=" * 60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
