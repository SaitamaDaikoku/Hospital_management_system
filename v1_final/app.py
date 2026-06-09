from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import date
import socket
import subprocess
import sys
import time

app = Flask(__name__)
app.secret_key = 'hospital_secret_key_2024'

app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'bruhboy7'
app.config['MYSQL_DB'] = 'hospital_db'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

MYSQL_SERVICE_NAME = 'MySQL80'
MYSQL_PORT = 3306


def is_mysql_reachable(host, port, timeout=1):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_mysql_running():
    host = app.config['MYSQL_HOST']
    if is_mysql_reachable(host, MYSQL_PORT):
        return True

    if sys.platform != 'win32':
        print("MySQL is not reachable on port 3306. Please start your MySQL server first.")
        return False

    print(f"MySQL is not reachable on {host}:{MYSQL_PORT}. Trying to start Windows service '{MYSQL_SERVICE_NAME}'...")
    result = subprocess.run(
        ['net', 'start', MYSQL_SERVICE_NAME],
        capture_output=True,
        text=True,
        shell=False
    )

    if result.returncode != 0:
        error_text = (result.stderr or result.stdout).strip()
        print(f"Could not start '{MYSQL_SERVICE_NAME}' automatically.")
        if error_text:
            print(error_text)
        print("Run this app as Administrator, or start MySQL manually with: net start MySQL80")
        return False

    for _ in range(10):
        if is_mysql_reachable(host, MYSQL_PORT):
            print("MySQL service started successfully.")
            return True
        time.sleep(1)

    print("MySQL service was started, but port 3306 is still not reachable.")
    return False

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def receptionist_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'receptionist':
            flash('Access denied. Receptionist only.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        cur.close()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['role'] = user['role']
            flash(f'Welcome back, {user["full_name"]}!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid credentials. Please try again.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) as count FROM patients")
    total_patients = cur.fetchone()['count']
    cur.execute("SELECT COUNT(*) as count FROM appointments WHERE appointment_date = CURDATE()")
    today_appointments = cur.fetchone()['count']
    cur.execute("SELECT COUNT(*) as count FROM doctors")
    total_doctors = cur.fetchone()['count']
    cur.execute("SELECT COALESCE(SUM(total),0) as revenue FROM billing WHERE status='paid' AND MONTH(billing_date)=MONTH(CURDATE())")
    monthly_revenue = cur.fetchone()['revenue']
    cur.execute("""
        SELECT a.*, p.first_name, p.last_name, u.full_name as doctor_name
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        JOIN doctors d ON a.doctor_id = d.id
        JOIN users u ON d.user_id = u.id
        WHERE a.appointment_date >= CURDATE()
        ORDER BY a.appointment_date, a.appointment_time LIMIT 5
    """)
    upcoming = cur.fetchall()
    cur.close()
    return render_template('dashboard.html',
        total_patients=total_patients,
        today_appointments=today_appointments,
        total_doctors=total_doctors,
        monthly_revenue=monthly_revenue,
        upcoming=upcoming)

@app.route('/patients')
@login_required
def patients():
    search = request.args.get('search', '')
    cur = mysql.connection.cursor()
    if search:
        cur.execute("""SELECT * FROM patients WHERE first_name LIKE %s OR last_name LIKE %s OR phone LIKE %s
                       ORDER BY created_at DESC""",
                    (f'%{search}%', f'%{search}%', f'%{search}%'))
    else:
        cur.execute("SELECT * FROM patients ORDER BY created_at DESC")
    patients_list = cur.fetchall()
    cur.close()
    return render_template('patients.html', patients=patients_list, search=search)

@app.route('/patients/add', methods=['GET', 'POST'])
@login_required
def add_patient():
    if request.method == 'POST':
        cur = mysql.connection.cursor()
        cur.execute("""INSERT INTO patients (first_name, last_name, dob, gender, phone, email, address,
                       blood_group, allergies, emergency_contact, emergency_phone)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (request.form['first_name'], request.form['last_name'],
                     request.form.get('dob') or None, request.form.get('gender'),
                     request.form.get('phone'), request.form.get('email'),
                     request.form.get('address'), request.form.get('blood_group'),
                     request.form.get('allergies'), request.form.get('emergency_contact'),
                     request.form.get('emergency_phone')))
        mysql.connection.commit()
        cur.close()
        flash('Patient added successfully!', 'success')
        return redirect(url_for('patients'))
    return render_template('patient_form.html', patient=None, action='Add')

@app.route('/patients/edit/<int:pid>', methods=['GET', 'POST'])
@login_required
def edit_patient(pid):
    cur = mysql.connection.cursor()
    if request.method == 'POST':
        cur.execute("""UPDATE patients SET first_name=%s, last_name=%s, dob=%s, gender=%s, phone=%s,
                       email=%s, address=%s, blood_group=%s, allergies=%s, emergency_contact=%s,
                       emergency_phone=%s WHERE id=%s""",
                    (request.form['first_name'], request.form['last_name'],
                     request.form.get('dob') or None, request.form.get('gender'),
                     request.form.get('phone'), request.form.get('email'),
                     request.form.get('address'), request.form.get('blood_group'),
                     request.form.get('allergies'), request.form.get('emergency_contact'),
                     request.form.get('emergency_phone'), pid))
        mysql.connection.commit()
        cur.close()
        flash('Patient updated successfully!', 'success')
        return redirect(url_for('patients'))
    cur.execute("SELECT * FROM patients WHERE id=%s", (pid,))
    patient = cur.fetchone()
    cur.close()
    return render_template('patient_form.html', patient=patient, action='Edit')

@app.route('/patients/delete/<int:pid>', methods=['POST'])
@login_required
def delete_patient(pid):
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM patients WHERE id=%s", (pid,))
    mysql.connection.commit()
    cur.close()
    flash('Patient deleted successfully.', 'success')
    return redirect(url_for('patients'))

@app.route('/patients/view/<int:pid>')
@login_required
def view_patient(pid):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM patients WHERE id=%s", (pid,))
    patient = cur.fetchone()
    cur.execute("""SELECT a.*, u.full_name as doctor_name, d.specialization
                   FROM appointments a JOIN doctors d ON a.doctor_id=d.id
                   JOIN users u ON d.user_id=u.id
                   WHERE a.patient_id=%s ORDER BY a.appointment_date DESC""", (pid,))
    appointments = cur.fetchall()
    cur.execute("SELECT * FROM billing WHERE patient_id=%s ORDER BY billing_date DESC", (pid,))
    bills = cur.fetchall()
    cur.close()
    return render_template('patient_view.html', patient=patient, appointments=appointments, bills=bills)

@app.route('/doctors')
@login_required
def doctors():
    cur = mysql.connection.cursor()
    cur.execute("SELECT d.*, u.full_name, u.email, u.username FROM doctors d JOIN users u ON d.user_id=u.id")
    doctors_list = cur.fetchall()
    cur.close()
    return render_template('doctors.html', doctors=doctors_list)

@app.route('/doctors/schedule/<int:did>')
@login_required
def doctor_schedule(did):
    cur = mysql.connection.cursor()
    cur.execute("SELECT d.*, u.full_name FROM doctors d JOIN users u ON d.user_id=u.id WHERE d.id=%s", (did,))
    doctor = cur.fetchone()
    cur.execute("""SELECT a.*, p.first_name, p.last_name FROM appointments a
                   JOIN patients p ON a.patient_id=p.id WHERE a.doctor_id=%s
                   AND a.appointment_date >= CURDATE() ORDER BY a.appointment_date, a.appointment_time""", (did,))
    schedule = cur.fetchall()
    cur.close()
    return render_template('doctor_schedule.html', doctor=doctor, schedule=schedule)

@app.route('/appointments')
@login_required
def appointments():
    cur = mysql.connection.cursor()
    cur.execute("""SELECT a.*, p.first_name, p.last_name, u.full_name as doctor_name, d.specialization
                   FROM appointments a JOIN patients p ON a.patient_id=p.id
                   JOIN doctors d ON a.doctor_id=d.id JOIN users u ON d.user_id=u.id
                   ORDER BY a.appointment_date DESC, a.appointment_time DESC""")
    appts = cur.fetchall()
    cur.close()
    return render_template('appointments.html', appointments=appts)

@app.route('/appointments/add', methods=['GET', 'POST'])
@login_required
def add_appointment():
    cur = mysql.connection.cursor()
    if request.method == 'POST':
        cur.execute("""INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, reason, status)
                       VALUES (%s,%s,%s,%s,%s,'scheduled')""",
                    (request.form['patient_id'], request.form['doctor_id'],
                     request.form['appointment_date'], request.form['appointment_time'],
                     request.form.get('reason')))
        mysql.connection.commit()
        cur.close()
        flash('Appointment scheduled!', 'success')
        return redirect(url_for('appointments'))
    cur.execute("SELECT id, first_name, last_name FROM patients ORDER BY first_name")
    patients_list = cur.fetchall()
    cur.execute("SELECT d.id, u.full_name, d.specialization FROM doctors d JOIN users u ON d.user_id=u.id")
    doctors_list = cur.fetchall()
    cur.close()
    return render_template('appointment_form.html', patients=patients_list, doctors=doctors_list,
                           appointment=None, action='Schedule')

@app.route('/appointments/update_status/<int:aid>', methods=['POST'])
@login_required
def update_appointment_status(aid):
    status = request.form.get('status')
    cur = mysql.connection.cursor()
    cur.execute("UPDATE appointments SET status=%s WHERE id=%s", (status, aid))
    mysql.connection.commit()
    cur.close()
    flash('Appointment status updated.', 'success')
    return redirect(url_for('appointments'))

@app.route('/appointments/delete/<int:aid>', methods=['POST'])
@login_required
def delete_appointment(aid):
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM appointments WHERE id=%s", (aid,))
    mysql.connection.commit()
    cur.close()
    flash('Appointment deleted.', 'success')
    return redirect(url_for('appointments'))

@app.route('/billing')
@login_required
def billing():
    cur = mysql.connection.cursor()
    cur.execute("""SELECT b.*, p.first_name, p.last_name
                   FROM billing b JOIN patients p ON b.patient_id=p.id
                   ORDER BY b.billing_date DESC""")
    bills = cur.fetchall()
    cur.close()
    return render_template('billing.html', bills=bills)

@app.route('/billing/add', methods=['GET', 'POST'])
@login_required
def add_billing():
    cur = mysql.connection.cursor()
    if request.method == 'POST':
        amount = float(request.form['amount'])
        discount = float(request.form.get('discount', 0))
        tax = float(request.form.get('tax', 0))
        total = amount - discount + tax
        cur.execute("""INSERT INTO billing (patient_id, appointment_id, description, amount, discount, tax,
                       total, status, payment_method, billing_date)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (request.form['patient_id'], request.form.get('appointment_id') or None,
                     request.form['description'], amount, discount, tax, total,
                     request.form.get('status', 'pending'), request.form.get('payment_method', 'cash'),
                     request.form.get('billing_date') or date.today()))
        mysql.connection.commit()
        cur.close()
        flash('Bill created successfully!', 'success')
        return redirect(url_for('billing'))
    cur.execute("SELECT id, first_name, last_name FROM patients ORDER BY first_name")
    patients_list = cur.fetchall()
    cur.execute("""SELECT a.id, p.first_name, p.last_name, a.appointment_date FROM appointments a
                   JOIN patients p ON a.patient_id=p.id ORDER BY a.appointment_date DESC""")
    appointments_list = cur.fetchall()
    cur.close()
    return render_template('billing_form.html', patients=patients_list, appointments=appointments_list)

@app.route('/billing/pay/<int:bid>', methods=['POST'])
@login_required
def mark_paid(bid):
    cur = mysql.connection.cursor()
    cur.execute("UPDATE billing SET status='paid', paid_date=CURDATE() WHERE id=%s", (bid,))
    mysql.connection.commit()
    cur.close()
    flash('Payment recorded.', 'success')
    return redirect(url_for('billing'))

@app.route('/billing/delete/<int:bid>', methods=['POST'])
@login_required
def delete_billing(bid):
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM billing WHERE id=%s", (bid,))
    mysql.connection.commit()
    cur.close()
    flash('Bill deleted.', 'success')
    return redirect(url_for('billing'))

if __name__ == '__main__':
    ensure_mysql_running()
    app.run(debug=True, port=5000)
