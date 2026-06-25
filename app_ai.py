"""
NİLÜFER BELEDİYESİ - PROFESYONEL ML ENTEGRELİ API
Flask Backend with AI-Powered Optimization
"""

import joblib
import json
import numpy as np
from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import sqlite3
from datetime import datetime
import threading
import queue
import time
import sys
sys.path.append('.')
from route_optimizer import RouteOptimizer

app = Flask(__name__, static_folder='public')
CORS(app)

# Modelleri yükle
try:
    fill_prediction_model = joblib.load('models/fill_prediction_model.pkl')
    fill_scaler = joblib.load('models/fill_scaler.pkl')
    
    with open('models/fill_model_metadata.json', 'r', encoding='utf-8') as f:
        model_metadata = json.load(f)
    
    print("✅ AI Modelleri başarıyla yüklendi!")
    print(f"   Model: {model_metadata['metrics']['model_name']}")
    print(f"   R² Score: {model_metadata['metrics']['r2_score']:.4f}")
    print(f"   MAE: {model_metadata['metrics']['mae']:.4f}")
    AI_ENABLED = True
except Exception as e:
    print(f"⚠️ AI Modelleri yüklenemedi: {e}")
    print("   Klasik mod kullanılacak.")
    AI_ENABLED = False

def get_db_connection():
    conn = sqlite3.connect('nilufer_waste.db')
    conn.row_factory = sqlite3.Row
    return conn

# ============ SSE - Gerçek Zamanlı Bildirim Sistemi ============
_alert_clients = []
_alert_clients_lock = threading.Lock()

def _container_monitor():
    """Her 30 saniyede kritik konteynerleri kontrol edip SSE istemcilerine gönderir."""
    while True:
        try:
            conn = get_db_connection()
            try:
                rows = conn.execute('''
                    SELECT c.container_id, c.current_fill_level, c.container_type,
                           n.neighborhood_name
                    FROM containers c
                    JOIN neighborhoods n ON c.neighborhood_id = n.neighborhood_id
                    WHERE c.current_fill_level >= 0.75
                    ORDER BY c.current_fill_level DESC
                    LIMIT 20
                ''').fetchall()
            finally:
                conn.close()

            if rows:
                event_data = json.dumps({
                    'type': 'container_alert',
                    'timestamp': datetime.now().isoformat(),
                    'alerts': [
                        {
                            'container_id': row['container_id'],
                            'fill_level': round(row['current_fill_level'] * 100, 1),
                            'container_type': row['container_type'],
                            'neighborhood': row['neighborhood_name'],
                            'alert_level': 'CRITICAL' if row['current_fill_level'] >= 0.90 else 'WARNING'
                        }
                        for row in rows
                    ]
                })
                with _alert_clients_lock:
                    dead = []
                    for q in _alert_clients:
                        try:
                            q.put_nowait(event_data)
                        except Exception:
                            dead.append(q)
                    for q in dead:
                        _alert_clients.remove(q)
        except Exception as e:
            app.logger.error(f"Container monitor hatası: {e}")

        time.sleep(30)

_monitor_thread = threading.Thread(target=_container_monitor, daemon=True)
_monitor_thread.start()

@app.route('/api/stream/alerts')
def stream_alerts():
    """SSE endpoint — kritik konteyner bildirimleri"""
    def generate():
        client_q = queue.Queue(maxsize=50)
        with _alert_clients_lock:
            _alert_clients.append(client_q)
        try:
            yield ': connected\n\n'
            while True:
                try:
                    data = client_q.get(timeout=25)
                    yield f'data: {data}\n\n'
                except queue.Empty:
                    yield ': keepalive\n\n'
        finally:
            with _alert_clients_lock:
                if client_q in _alert_clients:
                    _alert_clients.remove(client_q)

    return Response(
        generate(),
        content_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Access-Control-Allow-Origin': '*'
        }
    )

@app.route('/api/containers/critical')
def get_critical_containers():
    """Kritik doluluk seviyesindeki konteynerleri döndür (polling alternatifi)"""
    try:
        threshold = float(request.args.get('threshold', 0.75))
        threshold = max(0.0, min(1.0, threshold))
    except (ValueError, TypeError):
        threshold = 0.75

    conn = get_db_connection()
    try:
        rows = conn.execute('''
            SELECT c.container_id, c.current_fill_level, c.container_type,
                   n.neighborhood_name, c.latitude, c.longitude
            FROM containers c
            JOIN neighborhoods n ON c.neighborhood_id = n.neighborhood_id
            WHERE c.current_fill_level >= ?
            ORDER BY c.current_fill_level DESC
        ''', (threshold,)).fetchall()
        return jsonify({
            'critical_containers': [dict(r) for r in rows],
            'count': len(rows),
            'threshold': threshold,
            'timestamp': datetime.now().isoformat()
        })
    finally:
        conn.close()

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/admin')
def admin():
    return app.send_static_file('admin.html')

# Auth endpoints (demo - production'da JWT kullan)
@app.route('/api/auth/login', methods=['POST'])
def login():
    """Kullanıcı girişi (demo)"""
    try:
        data = request.get_json()
        tc_number = data.get('tc_number', '')
        password = data.get('password', '')
        
        # Demo için basit kontrol (production'da hash + database)
        if tc_number and password:
            return jsonify({
                'success': True,
                'message': 'Giriş başarılı',
                'user': {
                    'tc_number': tc_number,
                    'name': 'Demo Kullanıcı',
                    'phone': '555-123-4567',
                    'role': 'user'
                },
                'token': 'demo_token_12345'  # Production'da JWT
            })
        else:
            return jsonify({
                'success': False,
                'error': 'TC kimlik no ve şifre gerekli'
            }), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/register', methods=['POST'])
def register():
    """Kullanıcı kaydı (demo)"""
    try:
        data = request.get_json()
        name = data.get('name', '')
        tc_number = data.get('tc_number', '')
        phone = data.get('phone', '')
        password = data.get('password', '')
        
        # Demo için basit kontrol
        if name and tc_number and password:
            return jsonify({
                'success': True,
                'message': 'Kayıt başarılı! Giriş yapabilirsiniz.',
                'user': {
                    'name': name,
                    'tc_number': tc_number,
                    'phone': phone,
                    'role': 'user'
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Ad, TC kimlik no ve şifre gerekli'
            }), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/containers')
def get_containers():
    """Tüm konteynerleri getir"""
    conn = get_db_connection()
    try:
        containers = conn.execute('''
            SELECT c.*, n.neighborhood_name, n.population
            FROM containers c
            JOIN neighborhoods n ON c.neighborhood_id = n.neighborhood_id
        ''').fetchall()
        return jsonify([dict(row) for row in containers])
    finally:
        conn.close()

@app.route('/api/predict_fill/<int:container_id>')
def predict_fill_level(container_id):
    """Bir konteyner için doluluk tahmini yap"""
    if not AI_ENABLED:
        return jsonify({'error': 'AI servisi şu anda devre dışı', 'code': 'AI_DISABLED'}), 503

    if container_id <= 0:
        return jsonify({'error': 'Geçersiz konteyner ID'}), 400

    conn = get_db_connection()
    try:
        container = conn.execute('''
            SELECT c.*, n.population
            FROM containers c
            JOIN neighborhoods n ON c.neighborhood_id = n.neighborhood_id
            WHERE c.container_id = ?
        ''', (container_id,)).fetchone()

        if not container:
            return jsonify({'error': 'Konteyner bulunamadı'}), 404

        # data_preparation.py ile uyumlu type encoding
        type_map = {'400lt': 1, '770lt': 2, 'underground': 3, '5000lt': 4}
        container_type = container['container_type'].lower()
        type_encoded = next((v for k, v in type_map.items() if k in container_type), 2)

        last_collection = datetime.strptime(container['last_collection_date'], '%Y-%m-%d')
        days_since = (datetime.now() - last_collection).days

        X = np.array([[
            days_since,
            datetime.now().weekday(),
            datetime.now().month,
            1 if datetime.now().weekday() >= 5 else 0,
            3,
            type_encoded,
            2,
            5.0,
            container['current_fill_level']
        ]])

        # Eğitimde kullanılan scaler ile normalize et
        X_scaled = fill_scaler.transform(X)
        prediction = fill_prediction_model.predict(X_scaled)[0]
        prediction = float(np.clip(prediction, 0, 0.95))

        mae = model_metadata['metrics']['mae']
        confidence = max(0.0, min(1.0, 1.0 - mae))

        return jsonify({
            'container_id': container_id,
            'current_fill': float(container['current_fill_level']),
            'predicted_fill': prediction,
            'model': model_metadata['metrics']['model_name'],
            'confidence': confidence
        })
    except Exception as e:
        app.logger.error(f"predict_fill hatası (container {container_id}): {e}", exc_info=True)
        return jsonify({'error': 'Tahmin yapılamadı', 'code': 'PREDICTION_ERROR'}), 500
    finally:
        conn.close()

@app.route('/api/optimize-routes', methods=['POST'])
@app.route('/api/fleet/optimize-routes', methods=['GET', 'POST'])
def optimize_routes():
    """AI ile rotaları optimize et"""
    try:
        # Parametreler - GET ve POST için farklı
        if request.method == 'GET':
            try:
                min_priority = float(request.args.get('min_priority', 0.6))
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': 'Geçersiz min_priority değeri'}), 400
        else:
            data = request.get_json() or {}
            try:
                min_priority = float(data.get('min_priority', 0.6))
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': 'Geçersiz min_priority değeri'}), 400

        if not (0.0 <= min_priority <= 1.0):
            return jsonify({'success': False, 'error': 'min_priority 0 ile 1 arasında olmalıdır'}), 400
        
        print(f"\n🚀 Rota optimizasyonu başlıyor (min_priority={min_priority})...")
        
        # Route Optimizer oluştur
        optimizer = RouteOptimizer()
        
        # Yüksek öncelikli konteynerleri al
        containers = optimizer.get_high_priority_containers(min_priority=min_priority)
        print(f"   ✓ {len(containers)} konteyner bulundu")
        
        # Araçları al
        vehicles = optimizer.get_available_vehicles()
        print(f"   ✓ {len(vehicles)} araç bulundu")
        
        # Rotaları optimize et
        routes = optimizer.optimize_routes_by_priority(containers, vehicles)
        print(f"   ✓ {len(routes)} rota oluşturuldu")
        
        # İstatistikleri hesapla
        total_containers = sum(r.get('container_count', 0) for r in routes)
        total_distance = sum(r.get('total_distance_km', 0) for r in routes)
        total_time = sum(r.get('total_time_hours', 0) for r in routes)
        avg_capacity = np.mean([r.get('capacity_usage', 0) for r in routes]) if routes else 0
        
        return jsonify({
            'success': True,
            'routes': routes,
            'summary': {
                'total_routes': len(routes),
                'assigned_containers': total_containers,
                'total_distance_km': round(total_distance, 2),
                'total_time_hours': round(total_time, 2),
                'avg_capacity_usage': round(avg_capacity, 2)
            },
            'ai_enabled': AI_ENABLED,
            'model_info': model_metadata['metrics'] if AI_ENABLED else None
        })
    
    except Exception as e:
        app.logger.error(f"Rota optimizasyon hatası: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Rota optimizasyonu başarısız', 'code': 'ROUTE_OPT_ERROR'}), 500

@app.route('/api/model_info')
def model_info():
    """Model bilgilerini getir"""
    if not AI_ENABLED:
        return jsonify({'ai_enabled': False})
    
    return jsonify({
        'ai_enabled': True,
        'model_name': model_metadata['metrics']['model_name'],
        'r2_score': model_metadata['metrics']['r2_score'],
        'mae': model_metadata['metrics']['mae'],
        'rmse': model_metadata['metrics']['rmse'],
        'train_date': model_metadata['metrics']['timestamp'],
        'feature_importance': model_metadata['feature_importance']
    })

@app.route('/api/neighborhoods')
def get_neighborhoods():
    """Tüm mahalleleri getir"""
    conn = get_db_connection()
    try:
        neighborhoods = conn.execute('SELECT * FROM neighborhoods').fetchall()
        return jsonify([dict(row) for row in neighborhoods])
    finally:
        conn.close()

@app.route('/api/vehicles')
def get_vehicles():
    """Tüm araçları getir"""
    conn = get_db_connection()
    try:
        vehicles = conn.execute('''
            SELECT v.*, vt.type_name, vt.capacity_tons
            FROM vehicles v
            JOIN vehicle_types vt ON v.type_id = vt.type_id
        ''').fetchall()
        return jsonify([dict(row) for row in vehicles])
    finally:
        conn.close()

@app.route('/dashboard/stats')
def dashboard_stats():
    """Dashboard istatistikleri"""
    conn = get_db_connection()
    try:
        total_containers = conn.execute('SELECT COUNT(*) as count FROM containers').fetchone()['count']
        total_vehicles = conn.execute('SELECT COUNT(*) as count FROM vehicles WHERE status="active"').fetchone()['count']
        total_neighborhoods = conn.execute('SELECT COUNT(*) as count FROM neighborhoods').fetchone()['count']
        avg_fill = conn.execute('SELECT AVG(current_fill_level) as avg FROM containers').fetchone()['avg']
        high_priority = conn.execute('SELECT COUNT(*) as count FROM containers WHERE current_fill_level >= 0.7').fetchone()['count']

        return jsonify({
            'total_containers': total_containers,
            'full_containers': high_priority,
            'fill_rate': avg_fill if avg_fill else 0,
            'total_vehicles': total_vehicles,
            'neighborhoods': total_neighborhoods,
            'avg_fill_level': round(avg_fill * 100, 1) if avg_fill else 0,
            'high_priority_containers': high_priority
        })
    finally:
        conn.close()

@app.route('/api/reports', methods=['POST'])
def create_report():
    """Vatandaş şikayeti oluştur"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Geçersiz istek gövdesi'}), 400

        container_id = data.get('container_id')
        fill_level_estimate = data.get('fill_level_estimate', 0.8)
        issue_type = data.get('issue_type', 'FULL')
        notes = data.get('notes', '')
        latitude = data.get('latitude', 40.1885)
        longitude = data.get('longitude', 28.9784)
        neighborhood = data.get('neighborhood', '')

        valid_issue_types = {'FULL', 'OVERFLOW', 'DAMAGED', 'MISSING', 'ODOR', 'OTHER'}
        if issue_type not in valid_issue_types:
            issue_type = 'OTHER'

        try:
            fill_level_estimate = float(fill_level_estimate)
            fill_level_estimate = max(0.0, min(1.0, fill_level_estimate))
        except (ValueError, TypeError):
            fill_level_estimate = 0.8

        if notes:
            notes = str(notes)[:500]

        conn = get_db_connection()
        try:
            conn.execute('''
                ALTER TABLE citizen_reports ADD COLUMN issue_type TEXT DEFAULT 'FULL'
            ''')
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute('''
                ALTER TABLE citizen_reports ADD COLUMN status TEXT DEFAULT 'PENDING'
            ''')
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute('''
                ALTER TABLE citizen_reports ADD COLUMN neighborhood TEXT DEFAULT ''
            ''')
            conn.commit()
        except Exception:
            pass

        try:
            cursor = conn.execute('''
                INSERT INTO citizen_reports
                    (container_id, fill_level_estimate, latitude, longitude, notes,
                     issue_type, status, neighborhood, submitted_at)
                VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
            ''', (
                container_id,
                fill_level_estimate,
                latitude,
                longitude,
                notes,
                issue_type,
                neighborhood,
                datetime.now().isoformat()
            ))
            conn.commit()
            report_id = cursor.lastrowid
            return jsonify({
                'success': True,
                'report_id': report_id,
                'reference': f'NB-{datetime.now().year}-{report_id:04d}',
                'status': 'PENDING',
                'message': 'Bildiriminiz alındı. En kısa sürede değerlendirilecektir.',
                'estimated_response_hours': 4
            }), 201
        finally:
            conn.close()

    except Exception as e:
        app.logger.error(f"create_report hatası: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Bildirim kaydedilemedi'}), 500


@app.route('/api/reports', methods=['GET'])
def get_reports():
    """Şikayetleri listele (admin)"""
    conn = get_db_connection()
    try:
        status_filter = request.args.get('status', '')
        if status_filter and status_filter in ('PENDING', 'REVIEWED', 'RESOLVED', 'REJECTED'):
            rows = conn.execute('''
                SELECT r.*, c.container_type
                FROM citizen_reports r
                LEFT JOIN containers c ON r.container_id = c.container_id
                WHERE r.status = ?
                ORDER BY r.submitted_at DESC
                LIMIT 100
            ''', (status_filter,)).fetchall()
        else:
            rows = conn.execute('''
                SELECT r.*, c.container_type
                FROM citizen_reports r
                LEFT JOIN containers c ON r.container_id = c.container_id
                ORDER BY r.submitted_at DESC
                LIMIT 100
            ''').fetchall()
        return jsonify({'reports': [dict(r) for r in rows], 'count': len(rows)})
    finally:
        conn.close()


@app.route('/api/reports/stats', methods=['GET'])
def report_stats():
    """Şikayet istatistikleri"""
    conn = get_db_connection()
    try:
        total = conn.execute('SELECT COUNT(*) as c FROM citizen_reports').fetchone()['c']
        by_issue = conn.execute('''
            SELECT COALESCE(issue_type,'FULL') as issue_type, COUNT(*) as count
            FROM citizen_reports GROUP BY issue_type
        ''').fetchall()
        return jsonify({
            'total': total,
            'by_issue_type': [dict(r) for r in by_issue]
        })
    finally:
        conn.close()


def _ensure_fill_history_table():
    """container_fill_history tablosunu oluştur (yoksa)"""
    conn = get_db_connection()
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS container_fill_history (
                history_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                container_id INTEGER NOT NULL,
                fill_level   REAL NOT NULL,
                recorded_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                source       TEXT DEFAULT 'SYSTEM'
            )
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_fill_hist_cid_date
            ON container_fill_history(container_id, recorded_at DESC)
        ''')
        conn.commit()
    finally:
        conn.close()

_ensure_fill_history_table()


def _record_fill_snapshot():
    """Tüm konteynerlerin doluluk seviyesini history tablosuna kaydet (günde 1-2 kez)"""
    conn = get_db_connection()
    try:
        rows = conn.execute('SELECT container_id, current_fill_level FROM containers').fetchall()
        now = datetime.now().isoformat()
        conn.executemany(
            'INSERT INTO container_fill_history (container_id, fill_level, recorded_at, source) VALUES (?,?,?,?)',
            [(r['container_id'], r['current_fill_level'], now, 'SYSTEM') for r in rows]
        )
        conn.commit()
    finally:
        conn.close()

# İlk başlatmada anlık snapshot al
try:
    _record_fill_snapshot()
except Exception:
    pass


@app.route('/api/containers/<int:container_id>/history')
def container_fill_history(container_id):
    """Bir konteynerin doluluk geçmişini döndür"""
    if container_id <= 0:
        return jsonify({'error': 'Geçersiz konteyner ID'}), 400

    try:
        days = int(request.args.get('days', 30))
        days = max(1, min(90, days))
    except (ValueError, TypeError):
        days = 30

    conn = get_db_connection()
    try:
        container = conn.execute('''
            SELECT c.container_id, c.container_type, c.current_fill_level,
                   n.neighborhood_name
            FROM containers c
            JOIN neighborhoods n ON c.neighborhood_id = n.neighborhood_id
            WHERE c.container_id = ?
        ''', (container_id,)).fetchone()

        if not container:
            return jsonify({'error': 'Konteyner bulunamadı'}), 404

        history_rows = conn.execute('''
            SELECT fill_level, recorded_at, source
            FROM container_fill_history
            WHERE container_id = ?
              AND recorded_at >= datetime('now', ? || ' days')
            ORDER BY recorded_at ASC
        ''', (container_id, f'-{days}')).fetchall()

        history = [
            {'fill_level': round(r['fill_level'] * 100, 1),
             'recorded_at': r['recorded_at'],
             'source': r['source']}
            for r in history_rows
        ]

        # Trend hesapla
        fill_values = [r['fill_level'] for r in history_rows]
        trend = None
        if len(fill_values) >= 2:
            diffs = [fill_values[i+1] - fill_values[i] for i in range(len(fill_values)-1)]
            avg_daily = sum(diffs) / len(diffs)
            current = container['current_fill_level']
            if avg_daily > 0:
                hours_until_full = (0.95 - current) / avg_daily * 24 if avg_daily > 0 else None
                trend = {
                    'daily_fill_rate': round(avg_daily * 100, 2),
                    'direction': 'INCREASING' if avg_daily > 0.005 else ('DECREASING' if avg_daily < -0.005 else 'STABLE'),
                    'hours_until_full': round(hours_until_full) if hours_until_full and hours_until_full > 0 else None
                }

        return jsonify({
            'container_id': container_id,
            'container_type': container['container_type'],
            'neighborhood': container['neighborhood_name'],
            'current_fill_percent': round(container['current_fill_level'] * 100, 1),
            'period_days': days,
            'history': history,
            'trend': trend,
            'record_count': len(history)
        })
    finally:
        conn.close()


@app.route('/api/stats/dashboard')
def stats_dashboard():
    """Genel dashboard istatistikleri"""
    conn = get_db_connection()
    try:
        total_containers = conn.execute('SELECT COUNT(*) as c FROM containers').fetchone()['c']
        total_vehicles   = conn.execute('SELECT COUNT(*) as c FROM vehicles WHERE status="active"').fetchone()['c']
        total_hoods      = conn.execute('SELECT COUNT(*) as c FROM neighborhoods').fetchone()['c']
        avg_fill_row     = conn.execute('SELECT AVG(current_fill_level) as v FROM containers').fetchone()
        avg_fill         = avg_fill_row['v'] or 0.0

        critical_count  = conn.execute("SELECT COUNT(*) as c FROM containers WHERE current_fill_level >= 0.9").fetchone()['c']
        warning_count   = conn.execute("SELECT COUNT(*) as c FROM containers WHERE current_fill_level >= 0.7 AND current_fill_level < 0.9").fetchone()['c']
        normal_count    = conn.execute("SELECT COUNT(*) as c FROM containers WHERE current_fill_level < 0.7").fetchone()['c']

        fill_dist = conn.execute('''
            SELECT
                SUM(CASE WHEN current_fill_level < 0.3 THEN 1 ELSE 0 END) as empty,
                SUM(CASE WHEN current_fill_level >= 0.3 AND current_fill_level < 0.6 THEN 1 ELSE 0 END) as half,
                SUM(CASE WHEN current_fill_level >= 0.6 AND current_fill_level < 0.85 THEN 1 ELSE 0 END) as near_full,
                SUM(CASE WHEN current_fill_level >= 0.85 THEN 1 ELSE 0 END) as critical
            FROM containers
        ''').fetchone()

        top_hoods = conn.execute('''
            SELECT n.neighborhood_name, COUNT(c.container_id) as container_count,
                   AVG(c.current_fill_level) as avg_fill
            FROM neighborhoods n
            LEFT JOIN containers c ON n.neighborhood_id = c.neighborhood_id
            GROUP BY n.neighborhood_id, n.neighborhood_name
            ORDER BY avg_fill DESC
            LIMIT 8
        ''').fetchall()

        return jsonify({
            'summary': {
                'total_containers': total_containers,
                'total_vehicles': total_vehicles,
                'total_neighborhoods': total_hoods,
                'avg_fill_percent': round(avg_fill * 100, 1),
                'critical_containers': critical_count,
                'warning_containers': warning_count,
                'normal_containers': normal_count
            },
            'fill_distribution': {
                'empty': fill_dist['empty'] or 0,
                'half': fill_dist['half'] or 0,
                'near_full': fill_dist['near_full'] or 0,
                'critical': fill_dist['critical'] or 0
            },
            'top_neighborhoods': [
                {
                    'name': r['neighborhood_name'],
                    'container_count': r['container_count'],
                    'avg_fill_percent': round((r['avg_fill'] or 0) * 100, 1)
                }
                for r in top_hoods
            ],
            'timestamp': datetime.now().isoformat()
        })
    finally:
        conn.close()


@app.route('/containers/all')
def containers_all():
    """Tüm konteynerleri detaylı getir"""
    conn = get_db_connection()
    try:
        containers = conn.execute('''
            SELECT c.*, n.neighborhood_name, n.population
            FROM containers c
            JOIN neighborhoods n ON c.neighborhood_id = n.neighborhood_id
            ORDER BY c.current_fill_level DESC
        ''').fetchall()
        return jsonify([dict(row) for row in containers])
    finally:
        conn.close()

if __name__ == '__main__':
    print("="*80)
    print("🚀 NİLÜFER BELEDİYESİ - AI-POWERED ATIK YÖNETİM SİSTEMİ")
    print("="*80)
    print(f"\n📊 AI Durum: {'✅ Aktif' if AI_ENABLED else '⚠️ Devre Dışı'}")
    if AI_ENABLED:
        print(f"   Model: {model_metadata['metrics']['model_name']}")
        print(f"   Performans: R²={model_metadata['metrics']['r2_score']:.4f}")
    print("\n🌐 Sunucu Başlatılıyor...")
    print("   Admin Panel: http://localhost:5000/admin")
    print("   Ana Sayfa: http://localhost:5000/")
    print("="*80 + "\n")
    
    app.run(debug=True, port=5000, host='0.0.0.0')
