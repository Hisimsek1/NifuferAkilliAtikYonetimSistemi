"""
SQLite Veri Yükleme Script'i
Nilüfer Belediyesi Akıllı Atık Yönetim Sistemi
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random

DB_PATH = 'nilufer_waste.db'

def load_neighborhoods():
    """Mahalle verilerini yükle"""
    print("\n📍 Mahalle verileri yükleniyor...")
    
    df = pd.read_csv('data/mahalle_nufus.csv', encoding='utf-8-sig', sep=';')
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for _, row in df.iterrows():
        area_raw = row.get('alan')
        area = float(area_raw) if pd.notna(area_raw) else 2.0
        if not pd.notna(row.get('nufus')):
            continue
        nufus = int(str(row['nufus']).replace('.', ''))  # 4.371 -> 4371
        density = nufus / area if area > 0 else 5000
        
        cursor.execute("""
            INSERT OR IGNORE INTO neighborhoods (neighborhood_name, population, population_density, area_km2)
            VALUES (?, ?, ?, ?)
        """, (row['mahalle'], nufus, density, area))
    
    conn.commit()
    count = cursor.execute("SELECT COUNT(*) FROM neighborhoods").fetchone()[0]
    conn.close()
    
    print(f"✓ {count} mahalle yüklendi")

def load_vehicle_types():
    """Araç tiplerini yükle"""
    print("\n🚛 Araç tipleri yükleniyor...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    types = [
        ('Küçük Çöp Kamyonu', 3.0, 500),
        ('Büyük Çöp Kamyonu', 8.0, 800),
        ('Vinçli Araç', 1.0, 400)
    ]
    
    for name, capacity, cost in types:
        cursor.execute("""
            INSERT OR IGNORE INTO vehicle_types (type_name, capacity_tons, hourly_cost)
            VALUES (?, ?, ?)
        """, (name, capacity, cost))
    
    conn.commit()
    count = cursor.execute("SELECT COUNT(*) FROM vehicle_types").fetchone()[0]
    conn.close()
    
    print(f"✓ {count} araç tipi yüklendi")

def load_fleet():
    """Filo verilerini yükle"""
    print("\n🚗 Filo verileri yükleniyor...")
    
    df = pd.read_csv('data/fleet.csv', encoding='utf-8-sig')
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Tip ID'lerini al ve mapping oluştur
    type_map = {
        'Large Garbage Truck': 2,  # Büyük Çöp Kamyonu
        'Small Garbage Truck': 1,  # Küçük Çöp Kamyonu
        'Crane Vehicle': 3          # Vinçli Araç
    }
    
    for _, row in df.iterrows():
        vehicle_type = row['vehicle_type']
        type_id = type_map.get(vehicle_type, 2)  # Default: Büyük
        plate = f"{row['vehicle_id']}-{row['vehicle_name']}"
        
        cursor.execute("""
            INSERT OR IGNORE INTO vehicles (plate_number, type_id, status)
            VALUES (?, ?, 'active')
        """, (plate, type_id))
    
    conn.commit()
    count = cursor.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
    conn.close()
    
    print(f"✓ {count} araç yüklendi")

def load_containers():
    """Konteyner verilerini yükle"""
    print("\n🗑️ Konteyner verileri oluşturuluyor...")
    
    df = pd.read_csv('data/container_counts.csv', encoding='utf-8-sig', sep=';')
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Mahalle ID'lerini al
    cursor.execute("SELECT neighborhood_id, neighborhood_name FROM neighborhoods")
    neighborhood_map = {name: nid for nid, name in cursor.fetchall()}
    
    total_containers = 0
    
    for _, row in df.iterrows():
        mahalle = row['MAHALLE']
        neighborhood_id = neighborhood_map.get(mahalle)
        
        if not neighborhood_id:
            continue
        
        # Her mahalle için konteynerleri oluştur
        types = [
            ('underground', 'YERALTI KONTEYNER', 5000, 40.2, 28.9),
            ('770lt', '770 LT KONTEYNER', 770, 40.2, 28.9),
            ('400lt', '400 LT KONTEYNER', 400, 40.2, 28.9),
            ('plastic', 'PLASTİK', 240, 40.2, 28.9)
        ]
        
        for container_type, col_name, capacity, base_lat, base_lng in types:
            if col_name in df.columns:
                count = int(row[col_name]) if pd.notna(row[col_name]) else 0
                
                for i in range(count):
                    # Rastgele koordinatlar (mahalle içinde)
                    lat = base_lat + random.uniform(-0.02, 0.02)
                    lng = base_lng + random.uniform(-0.02, 0.02)
                    
                    # Son toplama tarihi (1-10 gün önce)
                    days_ago = random.randint(1, 10)
                    last_collection = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%d')
                    
                    # Doluluk seviyesi (max %95)
                    base_fill = days_ago * 0.08
                    random_fill = random.uniform(0, 0.15)
                    fill_level = min(0.95, base_fill + random_fill)
                    
                    cursor.execute("""
                        INSERT INTO containers 
                        (neighborhood_id, container_type, capacity_liters, latitude, longitude, 
                         last_collection_date, current_fill_level, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
                    """, (neighborhood_id, container_type, capacity, lat, lng, last_collection, fill_level))
                    
                    total_containers += 1
    
    conn.commit()
    conn.close()
    
    print(f"✓ {total_containers} konteyner oluşturuldu")

def load_tonnage_statistics():
    """Tonaj istatistiklerini yükle"""
    print("\n📊 Tonaj istatistikleri yükleniyor...")
    
    try:
        # CSV'yi satır satır oku (hatalı virgüllere karşı)
        df = pd.read_csv('data/tonnages.csv', encoding='utf-8-sig', on_bad_lines='skip')
    except Exception as e:
        print(f"⚠️ Tonaj verisi yüklenemedi: {e}")
        print("  Devam ediliyor...")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for _, row in df.iterrows():
        try:
            month = f"{row['AY']}-{row['YIL']}"
            surface = float(str(row['Yer Üstü Tonaj (TON)']).replace(',', '.')) if pd.notna(row.get('Yer Üstü Tonaj (TON)')) else 0
            underground = float(str(row['Yer Altı Tonaj (TON)']).replace(',', '.')) if pd.notna(row.get('Yer Altı Tonaj (TON)')) else 0
            total = float(str(row['Toplam Tonaj (TON)']).replace(',', '.')) if pd.notna(row.get('Toplam Tonaj (TON)')) else (surface + underground)
            
            cursor.execute("""
                INSERT OR IGNORE INTO tonnage_statistics (month, surface_tonnage, underground_tonnage, total_tonnage)
                VALUES (?, ?, ?, ?)
            """, (month, surface, underground, total))
        except Exception as e:
            continue  # Hatalı satırı atla
    
    conn.commit()
    count = cursor.execute("SELECT COUNT(*) FROM tonnage_statistics").fetchone()[0]
    conn.close()
    
    print(f"✓ {count} aylık tonaj verisi yüklendi")

def generate_collection_events():
    """Sentetik toplama olayları oluştur (model eğitimi için)"""
    print("\n🔄 Toplama olayları oluşturuluyor...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Konteynerleri al
    cursor.execute("SELECT container_id, capacity_liters FROM containers LIMIT 500")
    containers = cursor.fetchall()
    
    # Araçları al
    cursor.execute("SELECT vehicle_id FROM vehicles")
    vehicles = [v[0] for v in cursor.fetchall()]
    
    events_created = 0
    
    for container_id, capacity in containers:
        # Her konteyner için 1-3 toplama olayı
        num_events = random.randint(1, 3)
        
        for _ in range(num_events):
            # Rastgele tarih (son 60 gün)
            days_ago = random.randint(1, 60)
            collection_date = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%d')
            
            # Tonnage (kapasite ve doluluk seviyesine göre)
            fill_before = random.uniform(0.6, 0.95)
            tonnage = (capacity / 1000) * fill_before * random.uniform(0.8, 1.2)
            
            # Süre
            duration = random.randint(5, 20)
            
            # Rastgele araç
            vehicle_id = random.choice(vehicles) if vehicles else 1
            
            cursor.execute("""
                INSERT INTO collection_events 
                (container_id, vehicle_id, collection_date, tonnage_collected, 
                 fill_level_before, collection_duration_minutes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (container_id, vehicle_id, collection_date, tonnage, fill_before, duration))
            
            events_created += 1
    
    conn.commit()
    conn.close()
    
    print(f"✓ {events_created} toplama olayı oluşturuldu")

def main():
    """Ana fonksiyon"""
    print("=" * 60)
    print("NİLÜFER BELEDİYESİ - VERİ YÜKLEME")
    print("SQLite ile Gerçek Veriler")
    print("=" * 60)
    
    try:
        load_neighborhoods()
        load_vehicle_types()
        load_fleet()
        load_containers()
        load_tonnage_statistics()
        generate_collection_events()
        
        print("\n" + "=" * 60)
        print("✅ TÜM VERİLER BAŞARIYLA YÜKLENDİ!")
        print("=" * 60)
        print("\n📊 Özet:")
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        stats = {
            'Mahalleler': cursor.execute("SELECT COUNT(*) FROM neighborhoods").fetchone()[0],
            'Araçlar': cursor.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0],
            'Konteynerler': cursor.execute("SELECT COUNT(*) FROM containers").fetchone()[0],
            'Toplama Olayları': cursor.execute("SELECT COUNT(*) FROM collection_events").fetchone()[0],
            'Tonaj Kayıtları': cursor.execute("SELECT COUNT(*) FROM tonnage_statistics").fetchone()[0]
        }
        
        conn.close()
        
        for key, value in stats.items():
            print(f"  {key}: {value}")
        
        print("\n📋 Sıradaki adım: python train_model_sqlite.py")
        
    except Exception as e:
        print(f"\n❌ Hata: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
