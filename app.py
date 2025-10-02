from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = 'parking_app_secret_key_2024'

DATABASE = 'parking_app.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    conn = get_db_connection()
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

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['username'] == 'admin'
            if session['is_admin']:
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('user_dashboard'))
        else:
            flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        phone = request.form['phone']
        conn = get_db_connection()
        existing_user = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if existing_user:
            flash('Username already exists')
        else:
            hashed_password = generate_password_hash(password)
            conn.execute('INSERT INTO users (username, password, email, phone) VALUES (?, ?, ?, ?)',
                        (username, hashed_password, email, phone))
            conn.commit()
            flash('Registration successful! Please login.')
            conn.close()
            return redirect(url_for('login'))
        
        conn.close()
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    lots = conn.execute('SELECT * FROM parking_lots').fetchall()
    total_spots = conn.execute('SELECT COUNT(*) as count FROM parking_spots').fetchone()['count']
    occupied_spots = conn.execute('SELECT COUNT(*) as count FROM parking_spots WHERE status = "O"').fetchone()['count']
    total_users = conn.execute('SELECT COUNT(*) as count FROM users WHERE username != "admin"').fetchone()['count']
    conn.close()
    return render_template('admin_dashboard.html', 
                         lots=lots, 
                         total_spots=total_spots, 
                         occupied_spots=occupied_spots,
                         total_users=total_users)

@app.route('/admin/create_lot', methods=['GET', 'POST'])
def create_lot():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        address = request.form['address']
        pin_code = request.form['pin_code']
        max_spots = int(request.form['max_spots'])
        
        conn = get_db_connection()
        cursor = conn.execute('INSERT INTO parking_lots (prime_location_name, price, address, pin_code, maximum_number_of_spots) VALUES (?, ?, ?, ?, ?)',
                            (name, price, address, pin_code, max_spots))
        lot_id = cursor.lastrowid
        for i in range(max_spots):
            conn.execute('INSERT INTO parking_spots (lot_id) VALUES (?)', (lot_id,))
        
        conn.commit()
        conn.close()
        flash('Parking lot created successfully!')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('create_lot.html')

@app.route('/admin/edit_lot/<int:lot_id>', methods=['GET', 'POST'])
def edit_lot(lot_id):
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        address = request.form['address']
        pin_code = request.form['pin_code']
        max_spots = int(request.form['max_spots'])
        
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
        flash('Parking lot updated successfully!')
        return redirect(url_for('admin_dashboard'))
    lot = conn.execute('SELECT * FROM parking_lots WHERE id = ?', (lot_id,)).fetchone()
    conn.close()
    return render_template('edit_lot.html', lot=lot)

@app.route('/admin/delete_lot/<int:lot_id>')
def delete_lot(lot_id):
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    occupied_count = conn.execute('SELECT COUNT(*) as count FROM parking_spots WHERE lot_id = ? AND status = "O"', (lot_id,)).fetchone()['count']
    if occupied_count > 0:
        flash('Cannot delete lot with occupied spots!')
    else:
        conn.execute('DELETE FROM parking_spots WHERE lot_id = ?', (lot_id,))
        conn.execute('DELETE FROM parking_lots WHERE id = ?', (lot_id,))
        conn.commit()
        flash('Parking lot deleted successfully!')
    
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/view_spots/<int:lot_id>')
def view_spots(lot_id):
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    lot = conn.execute('SELECT * FROM parking_lots WHERE id = ?', (lot_id,)).fetchone()
    spots = conn.execute('''
        SELECT ps.*, r.user_id, u.username, r.parking_timestamp 
        FROM parking_spots ps 
        LEFT JOIN reservations r ON ps.id = r.spot_id AND r.status = "active"
        LEFT JOIN users u ON r.user_id = u.id 
        WHERE ps.lot_id = ?
    ''', (lot_id,)).fetchall()
    conn.close()
    
    return render_template('view_spots.html', lot=lot, spots=spots)

@app.route('/user/dashboard')
def user_dashboard():
    if not session.get('user_id') or session.get('is_admin'):
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    user_id = session['user_id']
    active_reservations = conn.execute('''
        SELECT r.*, ps.id as spot_number, pl.prime_location_name, pl.price
        FROM reservations r
        JOIN parking_spots ps ON r.spot_id = ps.id
        JOIN parking_lots pl ON ps.lot_id = pl.id
        WHERE r.user_id = ? AND r.status = "active"
    ''', (user_id,)).fetchall()
    parking_history = conn.execute('''
        SELECT r.*, ps.id as spot_number, pl.prime_location_name, pl.price
        FROM reservations r
        JOIN parking_spots ps ON r.spot_id = ps.id
        JOIN parking_lots pl ON ps.lot_id = pl.id
        WHERE r.user_id = ? AND r.status = "completed"
        ORDER BY r.parking_timestamp DESC LIMIT 10
    ''', (user_id,)).fetchall()
    
    conn.close()
    return render_template('user_dashboard.html', 
                         active_reservations=active_reservations,
                         parking_history=parking_history)

@app.route('/user/book_parking', methods=['GET', 'POST'])
def book_parking():
    if not session.get('user_id') or session.get('is_admin'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        lot_id = int(request.form['lot_id'])
        user_id = session['user_id']
        conn = get_db_connection()
        available_spot = conn.execute('SELECT * FROM parking_spots WHERE lot_id = ? AND status = "A" LIMIT 1', (lot_id,)).fetchone()
        
        if available_spot:
            conn.execute('UPDATE parking_spots SET status = "O" WHERE id = ?', (available_spot['id'],))
            conn.execute('INSERT INTO reservations (spot_id, user_id) VALUES (?, ?)', (available_spot['id'], user_id))
            conn.commit()
            flash('Parking spot booked successfully!')
        else:
            flash('No available spots in this lot!')
        conn.close()
        return redirect(url_for('user_dashboard'))
    
    conn = get_db_connection()
    lots_with_availability = conn.execute('''
        SELECT pl.*, COUNT(ps.id) as available_spots
        FROM parking_lots pl
        LEFT JOIN parking_spots ps ON pl.id = ps.lot_id AND ps.status = "A"
        GROUP BY pl.id
        HAVING available_spots > 0
    ''').fetchall()
    conn.close()
    
    return render_template('book_parking.html', lots=lots_with_availability)

@app.route('/user/release_spot/<int:reservation_id>')
def release_spot(reservation_id):
    if not session.get('user_id') or session.get('is_admin'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    reservation = conn.execute('SELECT * FROM reservations WHERE id = ? AND user_id = ?', 
                              (reservation_id, session['user_id'])).fetchone()
    if reservation:
        parking_time = datetime.now() - datetime.fromisoformat(reservation['parking_timestamp'])
        hours = parking_time.total_seconds() / 3600
        
        lot_price = conn.execute('''
            SELECT pl.price FROM parking_lots pl
            JOIN parking_spots ps ON pl.id = ps.lot_id
            WHERE ps.id = ?
        ''', (reservation['spot_id'],)).fetchone()['price']
        total_cost = hours * lot_price
        conn.execute('UPDATE parking_spots SET status = "A" WHERE id = ?', (reservation['spot_id'],))
        conn.execute('UPDATE reservations SET leaving_timestamp = ?, parking_cost = ?, status = "completed" WHERE id = ?',
                    (datetime.now(), total_cost, reservation_id))
        conn.commit()
        flash(f'Spot released successfully! Total cost: ₹{total_cost:.2f}')
    conn.close()
    return redirect(url_for('user_dashboard'))

if __name__ == '__main__':
    init_database()
    app.run(debug=True)