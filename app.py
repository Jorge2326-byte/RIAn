from flask import Flask, render_template, request, redirect, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import os
import psycopg2
from dotenv import load_dotenv
from datetime import datetime
from zoneinfo import ZoneInfo

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "rian123")


# ================== CONEXIÓN SUPABASE / POSTGRES ==================

def get_db_connection():
    return psycopg2.connect(
        os.environ.get("DATABASE_URL"),
        sslmode="require"
    )


# ================== UTILIDADES ==================

def categoria_meta(nombre):
    categoria = (nombre or "Sin categoría").strip().lower()

    mapa = {
        "alimentación": ("🍔", "cat-orange"),
        "alimentacion": ("🍔", "cat-orange"),
        "comida": ("🍔", "cat-orange"),
        "ropa": ("👕", "cat-yellow"),
        "educación": ("📚", "cat-cyan"),
        "educacion": ("📚", "cat-cyan"),
        "transporte": ("🚌", "cat-blue"),
        "ocio": ("🎮", "cat-pink"),
        "salud": ("💊", "cat-green"),
        "vivienda": ("🏠", "cat-orange"),
        "servicios": ("💡", "cat-blue"),
        "salario": ("💼", "cat-green"),
        "freelance": ("💻", "cat-cyan"),
        "otros": ("📦", "cat-brown"),
        "sin categoría": ("📦", "cat-brown"),
        "sin categoria": ("📦", "cat-brown"),
    }

    return mapa.get(categoria, ("📦", "cat-brown"))


def fecha_larga_es(fecha):
    meses = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]
    return f"{fecha.day} de {meses[fecha.month - 1]} de {fecha.year}"


def formato_fecha(fecha):
    if not fecha:
        return ""
    try:
        return fecha.strftime("%d/%m/%Y")
    except Exception:
        return str(fecha)


def formatear_monto(valor):
    try:
        valor = float(valor or 0)
        return "{:,.2f}".format(valor)
    except Exception:
        return "0.00"


@app.context_processor
def utilidades_globales():
    return {
        "formatear_monto": formatear_monto,
        "formato_fecha": formato_fecha,
        "fecha_larga_es": fecha_larga_es,
        "categoria_meta": categoria_meta
    }


# ================== LOGIN ==================

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form.get('correo', '').strip()
        password = request.form.get('password', '')

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            "SELECT id, nombre, correo, password FROM usuarios WHERE correo=%s",
            (correo,)
        )
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
        nombre = request.form.get('nombre', '').strip()
        correo = request.form.get('correo', '').strip()
        password = request.form.get('password', '')

        if not nombre or not correo or not password:
            flash('Todos los campos son obligatorios', 'error')
            return redirect('/register')

        conn = get_db_connection()
        cur = conn.cursor()

        try:
            cur.execute("SELECT id FROM usuarios WHERE correo=%s", (correo,))
            if cur.fetchone():
                flash('Correo ya registrado', 'error')
                return redirect('/register')

            password_hash = generate_password_hash(password)

            cur.execute(
                "INSERT INTO usuarios(nombre, correo, password) VALUES(%s,%s,%s)",
                (nombre, correo, password_hash)
            )
            conn.commit()

            flash('Cuenta creada correctamente', 'success')
            return redirect('/')

        finally:
            cur.close()
            conn.close()

    return render_template('register.html')


# ================== DASHBOARD ==================

@app.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session:
        return redirect('/')

    usuario_id = session['usuario_id']
    hoy = datetime.now()

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
    rows_movimientos = cur.fetchall()

    movimientos = []
    for mov in rows_movimientos:
        icono, color = categoria_meta(mov[4])
        movimientos.append({
            "id": mov[0],
            "tipo": mov[1],
            "descripcion": mov[2],
            "monto": float(mov[3] or 0),
            "categoria": mov[4] or "Sin categoría",
            "fecha": mov[5],
            "fecha_texto": formato_fecha(mov[5]),
            "icono": icono,
            "color": color
        })

    cur.execute("""
        SELECT categoria, COALESCE(SUM(monto), 0) AS total
        FROM movimientos
        WHERE usuario_id=%s
          AND tipo='Gasto'
          AND fecha >= date_trunc('month', CURRENT_DATE)
          AND fecha < date_trunc('month', CURRENT_DATE) + interval '1 month'
        GROUP BY categoria
        ORDER BY total DESC
        LIMIT 6
    """, (usuario_id,))
    rows_categorias = cur.fetchall()

    cur.close()
    conn.close()

    max_total = max([float(fila[1]) for fila in rows_categorias], default=1)

    categorias_resumen = []
    for categoria, total in rows_categorias:
        total = float(total or 0)
        icono, color = categoria_meta(categoria)
        width = 0 if max_total == 0 else round((total / max_total) * 100, 2)

        categorias_resumen.append({
            "nombre": categoria or "Sin categoría",
            "icono": icono,
            "color": color,
            "total": total,
            "width": max(width, 12) if total > 0 else 0
        })

    return render_template(
        'dashboard.html',
        usuario=session.get('usuario', 'Usuario'),
        correo_usuario=session.get('correo', ''),
        fecha_actual=fecha_larga_es(hoy),
        hoy_input=hoy.strftime('%Y-%m-%d'),
        ingresos=ingresos,
        gastos=gastos,
        balance=balance,
        total_movimientos=total_movimientos,
        categorias_resumen=categorias_resumen,
        movimientos=movimientos
    )


# ================== MOVIMIENTOS ==================

@app.route('/movimientos')
def movimientos():
    if 'usuario_id' not in session:
        return redirect('/')

    usuario_id = session['usuario_id']

    buscar = request.args.get('buscar', '').strip()
    filtro = request.args.get('filtro', 'Todos').strip()
    categoria_filtro = request.args.get('categoria', 'Todas las categorías').strip()

    conn = get_db_connection()
    cur = conn.cursor()

    query = """
        SELECT id, tipo, descripcion, monto, categoria, fecha
        FROM movimientos
        WHERE usuario_id = %s
    """

    params = [usuario_id]

    # Buscar por descripción o categoría
    if buscar:
        query += """
            AND (
                descripcion ILIKE %s
                OR categoria ILIKE %s
            )
        """
        params.append(f"%{buscar}%")
        params.append(f"%{buscar}%")

    # Filtrar por tipo: Ingreso o Gasto
    if filtro and filtro != "Todos":
        query += " AND tipo = %s"
        params.append(filtro)

    # Filtrar por categoría
    if categoria_filtro and categoria_filtro != "Todas las categorías":
        query += " AND categoria = %s"
        params.append(categoria_filtro)

    query += " ORDER BY fecha DESC, id DESC"

    cur.execute(query, tuple(params))
    rows = cur.fetchall()

    cur.close()
    conn.close()

    datos = []
    for mov in rows:
        icono, color = categoria_meta(mov[4])
        datos.append({
    "id": mov[0],
    "tipo": mov[1],
    "descripcion": mov[2],
    "monto": float(mov[3] or 0),
    "categoria": mov[4] or "Sin categoría",
    "fecha": mov[5],
    "fecha_texto": mov[5].strftime("%Y-%m-%d %H:%M:%S") if mov[5] else "",
    "fecha_corta": mov[5].strftime("%Y-%m-%d") if mov[5] else "",
    "hora_texto": mov[5].strftime("%I:%M %p") if mov[5] else "",
    "icono": icono,
    "color": color
})

    categorias_opciones = [
        "Alimentación",
        "Transporte",
        "Vivienda",
        "Salud",
        "Educación",
        "Ocio",
        "Ropa",
        "Salario",
        "Freelance",
        "Otros"
    ]

    return render_template(
        'movimientos.html',
        datos=datos,
        movimientos=datos,
        buscar=buscar,
        filtro=filtro,
        categoria_filtro=categoria_filtro,
        categorias_opciones=categorias_opciones,
        usuario=session.get('usuario', 'Usuario'),
        correo_usuario=session.get('correo', '')
    )

# ================== GUARDAR MOVIMIENTO ==================

@app.route('/guardar_movimiento', methods=['POST'])
def guardar_movimiento():
    if 'usuario_id' not in session:
        return redirect('/')

    tipo = request.form.get('tipo', '').strip()
    descripcion = request.form.get('descripcion', '').strip()
    categoria = request.form.get('categoria', 'Sin categoría').strip()

    fecha_form = request.form.get('fecha')
ahora = hora_colombia()

if fecha_form:
    fecha = f"{fecha_form} {ahora.strftime('%H:%M:%S')}"
else:
    fecha = ahora.strftime('%Y-%m-%d %H:%M:%S')

    if fecha_form:
        fecha = f"{fecha_form} {datetime.now().strftime('%H:%M:%S')}"
    else:
        fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        monto = float(request.form.get('monto', 0))
    except ValueError:
        flash('El monto no es válido', 'error')
        return redirect('/dashboard')

    if not tipo or not descripcion or monto <= 0:
        flash('Completa todos los campos correctamente', 'error')
        return redirect('/dashboard')

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO movimientos(usuario_id, tipo, descripcion, monto, categoria, fecha)
            VALUES(%s,%s,%s,%s,%s,%s)
        """, (
            session['usuario_id'],
            tipo,
            descripcion,
            monto,
            categoria,
            fecha
        ))
        conn.commit()
    finally:
        cur.close()
        conn.close()

    flash('Movimiento guardado correctamente', 'success')
    return redirect('/dashboard')

def hora_colombia():
    return datetime.now(ZoneInfo("America/Bogota"))
    
# ================== ELIMINAR MOVIMIENTO ==================

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

    flash('Movimiento eliminado', 'success')
    return redirect('/movimientos')


# ================== CATEGORÍAS ================== 

@app.route('/categorias')
def categorias():
    if 'usuario_id' not in session:
        return redirect('/')

    usuario_id = session['usuario_id']

    conn = get_db_connection()
    cur = conn.cursor()

    # Gastos reales del mes por categoría
    cur.execute("""
        SELECT categoria, COALESCE(SUM(monto), 0) AS total
        FROM movimientos
        WHERE usuario_id=%s
          AND tipo='Gasto'
          AND fecha >= date_trunc('month', CURRENT_DATE)
          AND fecha < date_trunc('month', CURRENT_DATE) + interval '1 month'
        GROUP BY categoria
        ORDER BY total DESC
    """, (usuario_id,))
    gastos_rows = cur.fetchall()

    # Presupuestos guardados por el usuario
    cur.execute("""
        SELECT categoria, limite_mensual
        FROM presupuestos
        WHERE usuario_id=%s
    """, (usuario_id,))
    presupuestos_rows = cur.fetchall()

    cur.close()
    conn.close()

    presupuestos_base = {
        "Alimentación": 400000,
        "Transporte": 150000,
        "Vivienda": 950000,
        "Salud": 200000,
        "Educación": 300000,
        "Ocio": 150000,
        "Ropa": 250000,
        "Otros": 100000
    }

    presupuestos_dict = {}
    for categoria, limite in presupuestos_rows:
        clave = (categoria or "Otros").strip().lower()
        presupuestos_dict[clave] = float(limite or 0)

    total_gastos = sum(float(row[1] or 0) for row in gastos_rows)

    categorias_reporte = []
    categorias_detalle = []

    for row in gastos_rows:
        nombre = row[0] or "Otros"
        clave = nombre.strip().lower()
        total = float(row[1] or 0)

        # Primero busca el presupuesto real guardado.
        # Si no existe, usa el presupuesto base.
        presupuesto = presupuestos_dict.get(
            clave,
            presupuestos_base.get(nombre, 100000)
        )

        porcentaje = 0
        if total_gastos > 0:
            porcentaje = round((total / total_gastos) * 100, 1)

        barra = 0
        if presupuesto > 0:
            barra = round((total / presupuesto) * 100, 1)

        barra = min(barra, 100)

        icono, color = categoria_meta(nombre)

        item = {
            "nombre": nombre,
            "icono": icono,
            "color": color,
            "total": total,
            "presupuesto": presupuesto,
            "porcentaje": porcentaje,
            "barra": barra
        }

        categorias_reporte.append(item)
        categorias_detalle.append(item)

    return render_template(
        'categorias.html',
        categorias_reporte=categorias_reporte,
        categorias_detalle=categorias_detalle,
        usuario=session.get('usuario', 'Usuario'),
        correo_usuario=session.get('correo', '')
    )

# ================== REPORTES ==================

@app.route('/reportes')
def reportes():
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
        SELECT categoria, COALESCE(SUM(monto),0)
        FROM movimientos
        WHERE usuario_id=%s
          AND tipo='Gasto'
          AND fecha >= date_trunc('month', CURRENT_DATE)
          AND fecha < date_trunc('month', CURRENT_DATE) + interval '1 month'
        GROUP BY categoria
        ORDER BY 2 DESC
    """, (usuario_id,))
    gastos_por_categoria = cur.fetchall()

    cur.execute("""
        SELECT tipo, COALESCE(SUM(monto),0)
        FROM movimientos
        WHERE usuario_id=%s
        GROUP BY tipo
    """, (usuario_id,))
    resumen = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        'reportes.html',
        ingresos=ingresos,
        gastos=gastos,
        balance=balance,
        gastos_por_categoria=gastos_por_categoria,
        resumen=resumen,
        usuario=session.get('usuario', 'Usuario'),
        correo_usuario=session.get('correo', '')
    )


# ================== ALERTAS ==================

@app.route('/alertas')
def alertas():
    if 'usuario_id' not in session:
        return redirect('/')

    usuario_id = session['usuario_id']

    # Presupuestos base para que siempre se vea como el diseño
    presupuestos_base = {
        "Alimentación": 400000,
        "Transporte": 150000,
        "Vivienda": 950000,
        "Salud": 200000,
        "Educación": 300000,
        "Ocio": 150000,
        "Ropa": 250000,
        "Otros": 100000
    }

    conn = get_db_connection()
    cur = conn.cursor()

    # Gastos reales del mes por categoría
    cur.execute("""
        SELECT categoria, COALESCE(SUM(monto), 0) AS total
        FROM movimientos
        WHERE usuario_id=%s
          AND tipo='Gasto'
          AND fecha >= date_trunc('month', CURRENT_DATE)
          AND fecha < date_trunc('month', CURRENT_DATE) + interval '1 month'
        GROUP BY categoria
    """, (usuario_id,))
    gastos_rows = cur.fetchall()

    # Presupuestos personalizados del usuario
    cur.execute("""
        SELECT categoria, limite_mensual
        FROM presupuestos
        WHERE usuario_id=%s
    """, (usuario_id,))
    presupuestos_rows = cur.fetchall()

    cur.close()
    conn.close()

    gastos_dict = {}
    for categoria, total in gastos_rows:
        clave = (categoria or "Otros").strip().lower()
        gastos_dict[clave] = float(total or 0)

    presupuestos_dict = {}
    for categoria, limite in presupuestos_rows:
        clave = (categoria or "Otros").strip().lower()
        presupuestos_dict[clave] = float(limite or 0)

    alertas_lista = []

    for categoria, limite_base in presupuestos_base.items():
        clave = categoria.strip().lower()

        gasto = gastos_dict.get(clave, 0)
        limite = presupuestos_dict.get(clave, limite_base)

        porcentaje = 0
        if limite > 0:
            porcentaje = round((gasto / limite) * 100)

        porcentaje_barra = min(porcentaje, 100)

        if porcentaje >= 100:
            estado_texto = "Presupuesto superado"
            alerta_clase = "danger"
            barra_clase = "danger"
            icono_estado = "🚨"
        elif porcentaje >= 80:
            estado_texto = "Cerca del límite"
            alerta_clase = "warning"
            barra_clase = "warning"
            icono_estado = "⚠️"
        else:
            estado_texto = "Dentro del presupuesto"
            alerta_clase = "success"
            barra_clase = "success"
            icono_estado = "✅"

        icono_categoria, color = categoria_meta(categoria)

        alertas_lista.append({
            "categoria": categoria,
            "icono_categoria": icono_categoria,
            "icono_estado": icono_estado,
            "estado_texto": estado_texto,
            "alerta_clase": alerta_clase,
            "barra_clase": barra_clase,
            "gasto": gasto,
            "limite": limite,
            "porcentaje": porcentaje,
            "porcentaje_barra": porcentaje_barra,
            "color": color
        })

    return render_template(
        'alertas.html',
        alertas=alertas_lista,
        datos=alertas_lista,
        usuario=session.get('usuario', 'Usuario'),
        correo_usuario=session.get('correo', '')
    )

# ================== GUARDAR PRESUPUESTO ==================

@app.route('/guardar_presupuesto', methods=['POST'])
def guardar_presupuesto():
    if 'usuario_id' not in session:
        return redirect('/')

    usuario_id = session['usuario_id']
    categoria = request.form.get('categoria', '').strip()

    # Tu HTML manda name="limite", no name="limite_mensual"
    limite_form = request.form.get('limite') or request.form.get('limite_mensual') or 0

    try:
        limite_mensual = float(limite_form)
    except ValueError:
        flash('El límite mensual no es válido', 'error')
        return redirect('/alertas')

    if not categoria or limite_mensual <= 0:
        flash('Completa correctamente el presupuesto', 'error')
        return redirect('/alertas')

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO presupuestos(usuario_id, categoria, limite_mensual)
            VALUES(%s,%s,%s)
            ON CONFLICT (usuario_id, categoria)
            DO UPDATE SET limite_mensual = EXCLUDED.limite_mensual
        """, (
            usuario_id,
            categoria,
            limite_mensual
        ))
        conn.commit()
    finally:
        cur.close()
        conn.close()

    flash('Presupuesto guardado correctamente', 'success')
    return redirect('/alertas')


# ================== LOGOUT ==================

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# ================== RUN LOCAL ==================

if __name__ == "__main__":
    app.run(debug=True)
