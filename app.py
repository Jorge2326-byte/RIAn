from flask import Flask, render_template, request, redirect, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import os
import psycopg2
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "rian123")

def get_db_connection():
    return psycopg2.connect(os.environ.get("DATABASE_URL"))

# ================== UTILIDADES ==================

def categoria_meta(nombre):
    categoria = (nombre or "Sin categoría").strip().lower()
    mapa = {
        "alimentación": ("🍔", "cat-orange"),
        "alimentacion": ("🍔", "cat-orange"),
        "ropa": ("👕", "cat-yellow"),
        "educación": ("📚", "cat-cyan"),
        "educacion": ("📚", "cat-cyan"),
        "transporte": ("🚌", "cat-blue"),
        "ocio": ("🎮", "cat-pink"),
        "salud": ("💊", "cat-green"),
        "vivienda": ("🏠", "cat-orange"),
        "otros": ("📦", "cat-brown"),
    }
    return mapa.get(categoria, ("📦", "cat-brown"))

# ================== LOGIN ==================

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form['correo'].strip()
        password = request.form['password']

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT id, nombre, correo, password FROM usuarios WHERE correo=%s", (correo,))
        user = cur.fetchone()

        cur.close()
        conn.close()

        if user and check_password_hash(user[3], password):
            session['usuario_id'] = user[0]
            session['usuario'] = user[1]
            session['correo'] = user[2]
            return redirect('/dashboard')

        flash('Correo o contraseña incorrectos', 'error')

    return render_template('login.html')

# ================== REGISTRO ==================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        correo = request.form['correo'].strip()
        password = request.form['password']

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT id FROM usuarios WHERE correo=%s", (correo,))
        if cur.fetchone():
            cur.close()
            conn.close()
            flash('Correo ya registrado', 'error')
            return redirect('/register')

        password_hash = generate_password_hash(password)

        cur.execute(
            "INSERT INTO usuarios(nombre, correo, password) VALUES(%s,%s,%s)",
            (nombre, correo, password_hash)
        )
        conn.commit()

        cur.close()
        conn.close()

        flash('Cuenta creada correctamente', 'success')
        return redirect('/')

    return render_template('register.html')

# ================== DASHBOARD ==================

@app.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session:
        return redirect('/')

    usuario_id = session['usuario_id']

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT COALESCE(SUM(monto),0)
        FROM movimientos
        WHERE usuario_id=%s
          AND tipo='Ingreso'
          AND fecha >= date_trunc('month', CURRENT_DATE)
          AND fecha < date_trunc('month', CURRENT_DATE) + interval '1 month'
    """, (usuario_id,))
    ingresos = float(cur.fetchone()[0] or 0)

    cur.execute("""
        SELECT COALESCE(SUM(monto),0)
        FROM movimientos
        WHERE usuario_id=%s
          AND tipo='Gasto'
          AND fecha >= date_trunc('month', CURRENT_DATE)
          AND fecha < date_trunc('month', CURRENT_DATE) + interval '1 month'
    """, (usuario_id,))
    gastos = float(cur.fetchone()[0] or 0)

    balance = ingresos - gastos

    cur.execute("""
        SELECT COUNT(*)
        FROM movimientos
        WHERE usuario_id=%s
          AND fecha >= date_trunc('month', CURRENT_DATE)
          AND fecha < date_trunc('month', CURRENT_DATE) + interval '1 month'
    """, (usuario_id,))
    total_movimientos = int(cur.fetchone()[0] or 0)

    cur.execute("""
        SELECT id, tipo, descripcion, monto, categoria, fecha
        FROM movimientos
        WHERE usuario_id=%s
        ORDER BY fecha DESC, id DESC
        LIMIT 5
    """, (usuario_id,))
    movimientos = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        'dashboard.html',
        ingresos=ingresos,
        gastos=gastos,
        balance=balance,
        total_movimientos=total_movimientos,
        movimientos=movimientos,
        usuario=session.get('usuario'),
        correo_usuario=session.get('correo')
    )

# ================== MOVIMIENTOS ==================

@app.route('/movimientos')
def movimientos():
    if 'usuario_id' not in session:
        return redirect('/')

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, tipo, descripcion, monto, categoria, fecha
        FROM movimientos
        WHERE usuario_id=%s
        ORDER BY fecha DESC
    """, (session['usuario_id'],))

    datos = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('movimientos.html', datos=datos)

# ================== GUARDAR ==================

@app.route('/guardar_movimiento', methods=['POST'])
def guardar_movimiento():
    if 'usuario_id' not in session:
        return redirect('/')

    fecha = request.form.get('fecha') or datetime.now().strftime('%Y-%m-%d')

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO movimientos(usuario_id, tipo, descripcion, monto, categoria, fecha)
            VALUES(%s,%s,%s,%s,%s,%s)
        """, (
            session['usuario_id'],
            request.form['tipo'],
            request.form['descripcion'],
            float(request.form['monto']),
            request.form['categoria'],
            fecha 
        ))
        conn.commit()
    finally:
        cur.close()
        conn.close()

    flash('Movimiento guardado', 'success')
    return redirect('/dashboard')

# ================== ELIMINAR ==================

@app.route('/eliminar/<int:id>')
def eliminar(id):
    if 'usuario_id' not in session:
        return redirect('/')

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            "DELETE FROM movimientos WHERE id=%s AND usuario_id=%s",
            (id, session['usuario_id'])
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

    return redirect('/movimientos')

# ================== LOGOUT ==================

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ================== RUN ==================

if __name__ == "__main__":
    app.run(debug=True)
