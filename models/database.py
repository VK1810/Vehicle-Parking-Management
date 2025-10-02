import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash

DATABASE = 'parking_app.db'

class DatabaseManager:
    @staticmethod
    def get_connection():
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        return conn
    
    @staticmethod
    def init_database():
        conn = DatabaseManager.get_connection()
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS parking_lots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prime_location_name TEXT NOT NULL,
                price REAL NOT NULL,
                address TEXT NOT NULL,
                pin_code TEXT NOT NULL,
                maximum_number_of_spots INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS parking_spots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lot_id INTEGER NOT NULL,
                status TEXT DEFAULT 'A',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (lot_id) REFERENCES parking_lots (id)
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                spot_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                parking_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                leaving_timestamp TIMESTAMP,
                parking_cost REAL,
                status TEXT DEFAULT 'active',
                FOREIGN KEY (spot_id) REFERENCES parking_spots (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        admin_exists = conn.execute('SELECT COUNT(*) FROM users WHERE username = ?', ('admin',)).fetchone()[0]
        if admin_exists == 0:
            admin_password = generate_password_hash('admin123')
            conn.execute('INSERT INTO users (username, password, email) VALUES (?, ?, ?)',
                        ('admin', admin_password, 'admin@parking.com'))
        
        conn.commit()
        conn.close()

class User:
    def __init__(self, id=None, username=None, password=None, email=None, phone=None):
        self.id = id
        self.username = username
        self.password = password
        self.email = email
        self.phone = phone
    
    @staticmethod
    def get_by_username(username):
        conn = DatabaseManager.get_connection()
        user_data = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        return user_data
    
    @staticmethod
    def create_user(username, password_hash, email, phone):
        conn = DatabaseManager.get_connection()
        cursor = conn.execute('INSERT INTO users (username, password, email, phone) VALUES (?, ?, ?, ?)',
                            (username, password_hash, email, phone))
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return user_id
    
    @staticmethod
    def get_all_users():
        conn = DatabaseManager.get_connection()
        users = conn.execute('SELECT * FROM users WHERE username != "admin"').fetchall()
        conn.close()
        return users

class ParkingLot:
    def __init__(self, id=None, name=None, price=None, address=None, pin_code=None, max_spots=None):
        self.id = id
        self.name = name
        self.price = price
        self.address = address
        self.pin_code = pin_code
        self.max_spots = max_spots
    
    @staticmethod
    def get_all_lots():
        conn = DatabaseManager.get_connection()
        lots = conn.execute('SELECT * FROM parking_lots').fetchall()
        conn.close()
        return lots
    
    @staticmethod
    def get_lot_by_id(lot_id):
        conn = DatabaseManager.get_connection()
        lot = conn.execute('SELECT * FROM parking_lots WHERE id = ?', (lot_id,)).fetchone()
        conn.close()
        return lot
    
    @staticmethod
    def create_lot(name, price, address, pin_code, max_spots):
        conn = DatabaseManager.get_connection()
        cursor = conn.execute('INSERT INTO parking_lots (prime_location_name, price, address, pin_code, maximum_number_of_spots) VALUES (?, ?, ?, ?, ?)',
                            (name, price, address, pin_code, max_spots))
        lot_id = cursor.lastrowid
        
        for i in range(max_spots):
            conn.execute('INSERT INTO parking_spots (lot_id) VALUES (?)', (lot_id,))
        
        conn.commit()
        conn.close()
        return lot_id
    
    @staticmethod
    def update_lot(lot_id, name, price, address, pin_code, max_spots):
        conn = DatabaseManager.get_connection()
        
        current_spots = conn.execute('SELECT COUNT(*) as count FROM parking_spots WHERE lot_id = ?', (lot_id,)).fetchone()['count']
        
        conn.execute('UPDATE parking_lots SET prime_location_name = ?, price = ?, address = ?, pin_code = ?, maximum_number_of_spots = ? WHERE id = ?',
                    (name, price, address, pin_code, max_spots, lot_id))
        
        if max_spots > current_spots:
            for i in range(max_spots - current_spots):
                conn.execute('INSERT INTO parking_spots (lot_id) VALUES (?)', (lot_id,))
        elif max_spots < current_spots:
            spots_to_remove = conn.execute('SELECT id FROM parking_spots WHERE lot_id = ? AND status = "A" LIMIT ?', 
                                         (lot_id, current_spots - max_spots)).fetchall()
            for spot in spots_to_remove:
                conn.execute('DELETE FROM parking_spots WHERE id = ?', (spot['id'],))
        
        conn.commit()
        conn.close()
    
    @staticmethod
    def delete_lot(lot_id):
        conn = DatabaseManager.get_connection()
        occupied_count = conn.execute('SELECT COUNT(*) as count FROM parking_spots WHERE lot_id = ? AND status = "O"', (lot_id,)).fetchone()['count']
        
        if occupied_count == 0:
            conn.execute('DELETE FROM parking_spots WHERE lot_id = ?', (lot_id,))
            conn.execute('DELETE FROM parking_lots WHERE id = ?', (lot_id,))
            conn.commit()
            conn.close()
            return True
        else:
            conn.close()
            return False
    
    @staticmethod
    def get_lots_with_availability():
        conn = DatabaseManager.get_connection()
        lots = conn.execute('''
            SELECT pl.*, COUNT(ps.id) as available_spots
            FROM parking_lots pl
            LEFT JOIN parking_spots ps ON pl.id = ps.lot_id AND ps.status = "A"
            GROUP BY pl.id
            HAVING available_spots > 0
        ''').fetchall()
        conn.close()
        return lots

class ParkingSpot:
    def __init__(self, id=None, lot_id=None, status='A'):
        self.id = id
        self.lot_id = lot_id
        self.status = status
    
    @staticmethod
    def get_spots_by_lot(lot_id):
        conn = DatabaseManager.get_connection()
        spots = conn.execute('''
            SELECT ps.*, r.user_id, u.username, r.parking_timestamp 
            FROM parking_spots ps 
            LEFT JOIN reservations r ON ps.id = r.spot_id AND r.status = "active"
            LEFT JOIN users u ON r.user_id = u.id 
            WHERE ps.lot_id = ?
        ''', (lot_id,)).fetchall()
        conn.close()
        return spots
    
    @staticmethod
    def get_available_spot(lot_id):
        conn = DatabaseManager.get_connection()
        spot = conn.execute('SELECT * FROM parking_spots WHERE lot_id = ? AND status = "A" LIMIT 1', (lot_id,)).fetchone()
        conn.close()
        return spot
    
    @staticmethod
    def update_spot_status(spot_id, status):
        conn = DatabaseManager.get_connection()
        conn.execute('UPDATE parking_spots SET status = ? WHERE id = ?', (status, spot_id))
        conn.commit()
        conn.close()

class Reservation:
    def __init__(self, id=None, spot_id=None, user_id=None, parking_timestamp=None, leaving_timestamp=None, parking_cost=None, status='active'):
        self.id = id
        self.spot_id = spot_id
        self.user_id = user_id
        self.parking_timestamp = parking_timestamp
        self.leaving_timestamp = leaving_timestamp
        self.parking_cost = parking_cost
        self.status = status
    
    @staticmethod
    def create_reservation(spot_id, user_id):
        conn = DatabaseManager.get_connection()
        cursor = conn.execute('INSERT INTO reservations (spot_id, user_id) VALUES (?, ?)', (spot_id, user_id))
        reservation_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return reservation_id
    
    @staticmethod
    def get_active_reservations(user_id):
        conn = DatabaseManager.get_connection()
        reservations = conn.execute('''
            SELECT r.*, ps.id as spot_number, pl.prime_location_name, pl.price
            FROM reservations r
            JOIN parking_spots ps ON r.spot_id = ps.id
            JOIN parking_lots pl ON ps.lot_id = pl.id
            WHERE r.user_id = ? AND r.status = "active"
        ''', (user_id,)).fetchall()
        conn.close()
        return reservations
    
    @staticmethod
    def get_user_history(user_id, limit=10):
        conn = DatabaseManager.get_connection()
        history = conn.execute('''
            SELECT r.*, ps.id as spot_number, pl.prime_location_name, pl.price
            FROM reservations r
            JOIN parking_spots ps ON r.spot_id = ps.id
            JOIN parking_lots pl ON ps.lot_id = pl.id
            WHERE r.user_id = ? AND r.status = "completed"
            ORDER BY r.parking_timestamp DESC LIMIT ?
        ''', (user_id, limit)).fetchall()
        conn.close()
        return history
    
    @staticmethod
    def release_reservation(reservation_id, user_id, total_cost):
        conn = DatabaseManager.get_connection()
        reservation = conn.execute('SELECT * FROM reservations WHERE id = ? AND user_id = ?', 
                                  (reservation_id, user_id)).fetchone()
        
        if reservation:
            conn.execute('UPDATE parking_spots SET status = "A" WHERE id = ?', (reservation['spot_id'],))
            conn.execute('UPDATE reservations SET leaving_timestamp = ?, parking_cost = ?, status = "completed" WHERE id = ?',
                        (datetime.now(), total_cost, reservation_id))
            conn.commit()
            conn.close()
            return True
        else:
            conn.close()
            return False
    
    @staticmethod
    def get_reservation_by_id(reservation_id, user_id):
        conn = DatabaseManager.get_connection()
        reservation = conn.execute('SELECT * FROM reservations WHERE id = ? AND user_id = ?', 
                                  (reservation_id, user_id)).fetchone()
        conn.close()
        return reservation