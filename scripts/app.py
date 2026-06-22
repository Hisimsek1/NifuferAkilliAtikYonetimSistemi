"""
Flask Backend API
Nilüfer Belediyesi Akıllı Atık Yönetim Sistemi
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import mysql.connector
from datetime import datetime, timedelta
import joblib
import pandas as pd
import numpy as np
import os
import json
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from functools import wraps

app = Flask(__name__, static_folder='public', static_url_path='')
CORS(app)

# Konfigürasyon
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'nilufer-waste-management-2024-dev-only')  # Üretimde SECRET_KEY env değişkenini ayarlayın!
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'your_password',  # ŞİFRENİZİ YAZIN
    'database': 'nilufer_waste_db'
}

# Model yükle
MODEL_PATH = 'models/fill_predictor.pkl'
model_data = None

try:
    model_data = joblib.load(MODEL_PATH)
    print(f"✓ Model yüklendi: {MODEL_PATH}")
except (FileNotFoundError, Exception) as e:
    print(f"⚠️ Model bulunamadı: {MODEL_PATH} - {e}")
    print("  Önce train_model.py'yi çalıştırın!")

# Veritabanı bağlantısı
def get_db():
    """Veritabanı bağlantısı oluştur"""
    return mysql.connector.connect(**DB_CONFIG)

# Auth decorator
def token_required(f):
    """JWT token kontrolü"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        
        if not token:
            return jsonify({'error': 'Token gerekli'}), 401
        
        try:
            token = token.split(' ')[1] if ' ' in token else token
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            request.user_id = data['user_id']
            request.user_role = data['role']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token süresi dolmuş'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Geçersiz token'}), 401
        
        return f(*args, **kwargs)
    
    return decorated

# ============== AUTHENTICATION ==============

@app.route('/api/auth/register', methods=['POST'])
def register():
    """Kullanıcı kaydı"""
    data = request.json
    
    required = ['name', 'email', 'password', 'phone']
    if not all(k in data for k in required):
        return jsonify({'error': 'Tüm alanları doldurun'}), 400
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Email kontrolü
        cursor.execute("SELECT user_id FROM users WHERE email = %s", (data['email'],))
        if cursor.fetchone():
            return jsonify({'error': 'Bu email zaten kayıtlı'}), 400
        
        # Hash password
        password_hash = generate_password_hash(data['password'])
        
        # Kullanıcıyı kaydet
        cursor.execute("""
            INSERT INTO users (name, email, password_hash, phone, role)
            VALUES (%s, %s, %s, %s, 'citizen')
        """, (data['name'], data['email'], password_hash, data['phone']))
        
        conn.commit()
        user_id = cursor.lastrowid
        
        # Token oluştur
        token = jwt.encode({
            'user_id': user_id,
            'role': 'citizen',
            'exp': datetime.utcnow() + timedelta(days=30)
        }, app.config['SECRET_KEY'])
        
        conn.close()
        
        return jsonify({
            'success': True,
            'token': token,
            'user': {
                'id': user_id,
                'name': data['name'],
                'email': data['email'],
                'role': 'citizen'
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    """Kullanıcı girişi"""
    data = request.json
    
    if not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Email ve şifre gerekli'}), 400
    
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT user_id, name, email, password_hash, role, trust_score
            FROM users WHERE email = %s
        """, (data['email'],))
        
        user = cursor.fetchone()
        conn.close()
        
        if not user or not check_password_hash(user['password_hash'], data['password']):
            return jsonify({'error': 'Email veya şifre hatalı'}), 401
        
        # Token oluştur
        token = jwt.encode({
            'user_id': user['user_id'],
            'role': user['role'],
            'exp': datetime.utcnow() + timedelta(days=30)
        }, app.config['SECRET_KEY'])
        
        return jsonify({
            'success': True,
            'token': token,
            'user': {
                'id': user['user_id'],
                'name': user['name'],
                'email': user['email'],
                'role': user['role'],
                'trust_score': float(user['trust_score'])
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============== CITIZEN REPORTS ==============

@app.route('/api/reports', methods=['POST'])
@token_required
def submit_report():
    """Vatandaş bildirimi gönder"""
    data = request.json
    
    required = ['container_id', 'fill_level_estimate', 'latitude', 'longitude']
    if not all(k in data for k in required):
        return jsonify({'error': 'Eksik bilgi'}), 400
    
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        # Konteyner var mı?
        cursor.execute("SELECT * FROM containers WHERE container_id = %s", 
                      (data['container_id'],))
        container = cursor.fetchone()
        
        if not container:
            return jsonify({'error': 'Konteyner bulunamadı'}), 404
        
        # Kullanıcı güven puanı
        cursor.execute("SELECT trust_score FROM users WHERE user_id = %s", 
                      (request.user_id,))
        user = cursor.fetchone()
        trust_score = float(user['trust_score']) if user else 0.5
        
        # Model tahmini al
        prediction = None
        if model_data:
            prediction = get_prediction_for_container(data['container_id'])
        
        # Tahmin farkı
        prediction_diff = None
        if prediction:
            prediction_diff = abs(data['fill_level_estimate'] - prediction['fill_probability'])
        
        # Fotoğraf gerekli mi?
        photo_required = trust_score < 0.7
        
        if photo_required and not data.get('photo_url'):
            return jsonify({
                'error': 'Güven puanınız düşük olduğu için fotoğraf gerekli',
                'photo_required': True
            }), 400
        
        # Bildirimi kaydet
        cursor.execute("""
            INSERT INTO citizen_reports
            (user_id, container_id, fill_level_estimate, photo_url, 
             latitude, longitude, notes, prediction_diff)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            request.user_id,
            data['container_id'],
            data['fill_level_estimate'],
            data.get('photo_url'),
            data['latitude'],
            data['longitude'],
            data.get('notes'),
            prediction_diff
        ))
        
        report_id = cursor.lastrowid
        
        # Konteyner doluluk seviyesini güncelle
        new_fill = (container['current_fill_level'] * 0.7 + 
                   data['fill_level_estimate'] * 0.3)
        
        cursor.execute("""
            UPDATE containers 
            SET current_fill_level = %s
            WHERE container_id = %s
        """, (new_fill, data['container_id']))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'report_id': report_id,
            'trust_score': trust_score,
            'prediction': prediction,
            'photo_required': photo_required
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/validate/<int:report_id>', methods=['POST'])
@token_required
def validate_report(report_id):
    """Bildirimi doğrula (toplama sonrası)"""
    data = request.json
    
    if request.user_role != 'admin':
        return jsonify({'error': 'Yetkisiz'}), 403
    
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        # Bildirimi al
        cursor.execute("""
            SELECT * FROM citizen_reports WHERE report_id = %s
        """, (report_id,))
        
        report = cursor.fetchone()
        if not report:
            return jsonify({'error': 'Bildirim bulunamadı'}), 404
        
        # Doğruluğu güncelle
        actual_full = data.get('actual_full', False)
        
        cursor.execute("""
            UPDATE citizen_reports
            SET is_verified = TRUE, verified_at = NOW(), actual_full = %s
            WHERE report_id = %s
        """, (actual_full, report_id))
        
        # Güven puanını güncelle (stored procedure)
        cursor.execute("CALL update_user_trust_score(%s)", (report['user_id'],))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============== PREDICTIONS ==============

@app.route('/api/predict/<int:container_id>', methods=['GET'])
def predict_container(container_id):
    """Tek konteyner için tahmin"""
    if not model_data:
        return jsonify({'error': 'Model yüklü değil'}), 503
    
    try:
        prediction = get_prediction_for_container(container_id)
        
        if prediction:
            return jsonify(prediction)
        else:
            return jsonify({'error': 'Konteyner bulunamadı'}), 404
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/predict/neighborhood/<int:neighborhood_id>', methods=['GET'])
def predict_neighborhood(neighborhood_id):
    """Mahalle için tüm konteyner tahminleri"""
    if not model_data:
        return jsonify({'error': 'Model yüklü değil'}), 503
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT container_id FROM containers
            WHERE neighborhood_id = %s AND status = 'active'
        """, (neighborhood_id,))
        
        container_ids = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        predictions = []
        for cid in container_ids:
            pred = get_prediction_for_container(cid)
            if pred:
                predictions.append(pred)
        
        return jsonify({
            'neighborhood_id': neighborhood_id,
            'total_containers': len(predictions),
            'full_containers': sum(1 for p in predictions if p['is_full']),
            'predictions': predictions
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def get_prediction_for_container(container_id):
    """Konteyner için tahmin hesapla"""
    if not model_data:
        return None
    
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        # Konteyner bilgilerini çek
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
            WHERE c.container_id = %s
        """, (container_id,))
        
        container = cursor.fetchone()
        conn.close()
        
        if not container:
            return None
        
        # Özellikleri oluştur
        features = engineer_features(container)
        
        # Tahmin yap
        model = model_data['model']
        probabilities = model.predict_proba([features])[0]
        fill_probability = probabilities[1]
        
        return {
            'container_id': container_id,
            'neighborhood': container['neighborhood_name'],
            'container_type': container['container_type'],
            'capacity_liters': container['capacity_liters'],
            'current_fill_level': float(container['current_fill_level']),
            'fill_probability': float(fill_probability),
            'is_full': bool(fill_probability >= 0.75),
            'confidence': float(max(probabilities)),
            'latitude': float(container['latitude']),
            'longitude': float(container['longitude']),
            'last_collection': container['last_collection_date'].isoformat() if container['last_collection_date'] else None,
            'model_version': model_data['version'],
            'prediction_timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"Prediction error: {e}")
        return None

def engineer_features(container):
    """Özellikleri oluştur (train_model.py ile aynı mantık)"""
    features = []
    
    # Zaman tabanlı
    if container['last_collection_date']:
        hours_since = (datetime.now() - container['last_collection_date']).total_seconds() / 3600
    else:
        hours_since = 168  # 1 hafta
    
    features.append(hours_since)
    features.append(hours_since / 24)  # days_since_collection
    
    # Tarih özellikleri
    now = datetime.now()
    features.append(now.weekday())  # day_of_week
    features.append(int(now.weekday() >= 5))  # is_weekend
    features.append(now.month)  # month
    
    # Mevsim
    month = now.month
    if month in [12, 1, 2]:
        season = 0
    elif month in [3, 4, 5]:
        season = 1
    elif month in [6, 7, 8]:
        season = 2
    else:
        season = 3
    features.append(season)
    
    # Konteyner
    features.append(container['capacity_liters'])
    
    # Tip encoding
    type_map = {'underground': 4, '770lt': 3, '400lt': 2, 'plastic': 1}
    features.append(type_map.get(container['container_type'], 2))
    
    # Nüfus
    features.append(container['population'] if container['population'] else 10000)
    features.append(container['population_density'] if container['population_density'] else 5000)
    features.append(container['area_km2'] if container['area_km2'] else 2.0)
    
    # Tarihsel (default değerler)
    features.append(0.5)  # avg_tonnage
    features.append(0.5)  # avg_fill_before
    features.append(10)   # collection_count
    features.append(0.5)  # capacity_usage_rate
    
    return features

# ============== DASHBOARD ==============

@app.route('/api/dashboard/stats', methods=['GET'])
def dashboard_stats():
    """Dashboard istatistikleri"""
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        # Toplam konteyner
        cursor.execute("SELECT COUNT(*) as count FROM containers WHERE status='active'")
        total_containers = cursor.fetchone()['count']
        
        # Dolu konteynerler
        cursor.execute("""
            SELECT COUNT(*) as count FROM containers 
            WHERE status='active' AND current_fill_level >= 0.75
        """)
        full_containers = cursor.fetchone()['count']
        
        # Bugünkü bildirimler
        cursor.execute("""
            SELECT COUNT(*) as count FROM citizen_reports 
            WHERE DATE(submitted_at) = CURDATE()
        """)
        today_reports = cursor.fetchone()['count']
        
        # Bugünkü toplanılanlar
        cursor.execute("""
            SELECT COUNT(*) as count FROM collection_events 
            WHERE DATE(collection_date) = CURDATE()
        """)
        today_collections = cursor.fetchone()['count']
        
        # Bu ay tonaj
        cursor.execute("""
            SELECT SUM(total_tonnage) as total
            FROM tonnage_statistics
            WHERE YEAR(month) = YEAR(CURDATE()) 
            AND MONTH(month) = MONTH(CURDATE())
        """)
        month_tonnage = cursor.fetchone()['total'] or 0
        
        conn.close()
        
        return jsonify({
            'total_containers': total_containers,
            'full_containers': full_containers,
            'fill_rate': full_containers / total_containers if total_containers > 0 else 0,
            'today_reports': today_reports,
            'today_collections': today_collections,
            'month_tonnage': float(month_tonnage)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/leaderboard', methods=['GET'])
def leaderboard():
    """Kullanıcı liderlik tablosu"""
    try:
        limit = request.args.get('limit', 10, type=int)
        
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT user_id, name, trust_score, total_reports
            FROM users
            WHERE role = 'citizen' AND total_reports > 0
            ORDER BY trust_score DESC, total_reports DESC
            LIMIT %s
        """, (limit,))
        
        users = cursor.fetchall()
        conn.close()
        
        return jsonify({
            'leaderboard': [
                {
                    'rank': idx + 1,
                    'name': u['name'],
                    'trust_score': float(u['trust_score']),
                    'total_reports': u['total_reports']
                }
                for idx, u in enumerate(users)
            ]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============== SIMULATION ==============

@app.route('/api/simulate', methods=['POST'])
@token_required
def simulate():
    """Filo simülasyonu"""
    if request.user_role != 'admin':
        return jsonify({'error': 'Yetkisiz'}), 403
    
    data = request.json
    
    try:
        # Senaryo parametreleri
        scenario = data.get('scenario', {})
        small_trucks = scenario.get('small_trucks', 5)
        large_trucks = scenario.get('large_trucks', 20)
        crane_vehicles = scenario.get('crane_vehicles', 10)
        
        # Basit simülasyon (gerçek algoritmayı burada uygulayın)
        # Şimdilik tahmin: her araç günde ortalama 8 saat çalışır
        
        total_capacity = (small_trucks * 3 + large_trucks * 8 + crane_vehicles * 1) * 8
        
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        # Dolu konteynerleri say
        cursor.execute("""
            SELECT COUNT(*) as count FROM containers 
            WHERE status='active' AND current_fill_level >= 0.75
        """)
        full_containers = cursor.fetchone()['count']
        
        # Tahmini toplama süresi
        estimated_hours = (full_containers / total_capacity) * 8 if total_capacity > 0 else 24
        estimated_cost = (small_trucks * 500 + large_trucks * 800 + crane_vehicles * 400)
        
        # Simülasyonu kaydet
        cursor.execute("""
            INSERT INTO simulation_runs
            (admin_user_id, scenario_params, estimated_cost, estimated_time_hours)
            VALUES (%s, %s, %s, %s)
        """, (
            request.user_id,
            json.dumps(scenario),
            estimated_cost,
            estimated_hours
        ))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'results': {
                'total_vehicles': small_trucks + large_trucks + crane_vehicles,
                'small_trucks': small_trucks,
                'large_trucks': large_trucks,
                'crane_vehicles': crane_vehicles,
                'estimated_hours': round(estimated_hours, 2),
                'estimated_cost': estimated_cost,
                'containers_to_collect': full_containers,
                'efficiency': min(100, (total_capacity / full_containers * 100) if full_containers > 0 else 100)
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============== STATIC FILES ==============

@app.route('/')
def index():
    """Ana sayfa"""
    return send_from_directory('public', 'index.html')

@app.route('/admin')
def admin():
    """Admin paneli"""
    return send_from_directory('public', 'admin.html')

# ============== MAIN ==============

if __name__ == '__main__':
    print("=" * 60)
    print("NİLÜFER BELEDİYESİ - BACKEND API")
    print("Akıllı Atık Yönetim Sistemi")
    print("=" * 60)
    print(f"\n✓ Model durumu: {'Yüklü' if model_data else 'YÜKLENMEDİ'}")
    print(f"✓ Veritabanı: {DB_CONFIG['database']}")
    print(f"✓ Port: 5000")
    print("\n🌐 URL'ler:")
    print("  Vatandaş Paneli: http://localhost:5000/")
    print("  Admin Paneli: http://localhost:5000/admin")
    print("  API Docs: http://localhost:5000/api/")
    print("\n" + "=" * 60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
