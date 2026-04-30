from flask import Flask, render_template, request, redirect, session, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mysqldb import MySQL

app = Flask(__name__)
app.secret_key = "rian123"

# CONEXION MYSQL
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'rian_db'
app.config['MYSQL_PORT'] = 3307

mysql = MySQL(app)

from datetime import datetime

MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]

DIAS_ES = [
    "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"
]

def fecha_larga_es(fecha):
    return f"{DIAS_ES[fecha.weekday()]}, {fecha.day} de {MESES_ES[fecha.month - 1]} de {fecha.year}"

def formatear_monto(valor):
    try:
        return "{:,.0f}".format(float(valor)).replace(",", ".")
    except:
        return "0"

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
    "salario": ("💼", "cat-green"),
    "freelance": ("🧾", "cat-cyan"),
    "ventas": ("🛒", "cat-orange"),
    "inversiones": ("📈", "cat-blue"),
    "otros ingresos": ("💰", "cat-green"),
    "hogar": ("🏠", "cat-yellow"),
    "servicios": ("💡", "cat-blue"),
    "otros": ("📦", "cat-brown"),
}

    return mapa.get(categoria, ("📦", "cat-brown"))

@app.context_processor
def utility_processor():
    return dict(formatear_monto=formatear_monto) 



# LOGIN
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form['correo'].strip()
        password = request.form['password']

        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT id, nombre, correo, password FROM usuarios WHERE correo=%s",
            (correo,)
        )
        user = cur.fetchone()

        if user and check_password_hash(user[3], password):
            session['usuario_id'] = user[0]
            session['usuario'] = user[1]
            session['correo'] = user[2] 
            return redirect('/dashboard')

        flash('Correo o contraseña incorrectos', 'error')
        return render_template('login.html', correo=correo)

    return render_template('login.html')

# REGISTRO
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        correo = request.form['correo'].strip()
        password = request.form['password']

        if len(password) < 6:
            flash('La contraseña debe tener al menos 6 caracteres', 'error')
            return render_template('register.html', nombre=nombre, correo=correo)

        cur = mysql.connection.cursor()

        cur.execute("SELECT id FROM usuarios WHERE correo=%s", (correo,))
        existe = cur.fetchone()

        if existe:
            flash('Este correo ya está registrado', 'error')
            return render_template('register.html', nombre=nombre, correo=correo)

        password_segura = generate_password_hash(password)

        cur.execute(
            "INSERT INTO usuarios(nombre, correo, password) VALUES(%s, %s, %s)",
            (nombre, correo, password_segura)
        )
        mysql.connection.commit()

        flash('Cuenta creada correctamente. Ahora puedes iniciar sesión.', 'success')
        return redirect('/')

    return render_template('register.html')

# DASHBOARD
@app.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session:
        return redirect('/')

    usuario_id = session['usuario_id']
    hoy = datetime.now()

    cur = mysql.connection.cursor()

    # Ingresos del mes
    cur.execute("""
        SELECT IFNULL(SUM(monto), 0)
        FROM movimientos
        WHERE usuario_id = %s
          AND tipo = 'Ingreso'
          AND MONTH(fecha) = MONTH(CURDATE())
          AND YEAR(fecha) = YEAR(CURDATE())
    """, (usuario_id,))
    ingresos = float(cur.fetchone()[0] or 0)

    # Gastos del mes
    cur.execute("""
        SELECT IFNULL(SUM(monto), 0)
        FROM movimientos
        WHERE usuario_id = %s
          AND tipo = 'Gasto'
          AND MONTH(fecha) = MONTH(CURDATE())
          AND YEAR(fecha) = YEAR(CURDATE())
    """, (usuario_id,))
    gastos = float(cur.fetchone()[0] or 0)

    balance = ingresos - gastos

    # Total de movimientos del mes
    cur.execute("""
        SELECT COUNT(*)
        FROM movimientos
        WHERE usuario_id = %s
          AND MONTH(fecha) = MONTH(CURDATE())
          AND YEAR(fecha) = YEAR(CURDATE())
    """, (usuario_id,))
    total_movimientos = int(cur.fetchone()[0] or 0)

    # Últimos movimientos
    cur.execute("""
        SELECT tipo, descripcion, monto, categoria, fecha
        FROM movimientos
        WHERE usuario_id = %s
        ORDER BY fecha DESC, id DESC
        LIMIT 5
    """, (usuario_id,))
    rows_movimientos = cur.fetchall()

    movimientos = []
    for tipo, descripcion, monto, categoria, fecha in rows_movimientos:
        icono, _ = categoria_meta(categoria)
        movimientos.append({
            "tipo": tipo,
            "descripcion": descripcion,
            "monto": float(monto or 0),
            "categoria": categoria or "Sin categoría",
            "icono": icono,
            "fecha_texto": fecha.strftime("%d/%m/%Y") if fecha else ""
        })

    # Gastos por categoría
    cur.execute("""
        SELECT categoria, IFNULL(SUM(monto), 0) AS total
        FROM movimientos
        WHERE usuario_id = %s
          AND tipo = 'Gasto'
          AND MONTH(fecha) = MONTH(CURDATE())
          AND YEAR(fecha) = YEAR(CURDATE())
        GROUP BY categoria
        ORDER BY total DESC
        LIMIT 6
    """, (usuario_id,))
    rows_categorias = cur.fetchall()

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

# MOVIMIENTOS
@app.route('/movimientos')
def movimientos():
    if 'usuario_id' not in session:
        return redirect('/')

    usuario_id = session['usuario_id']

    buscar = request.args.get('buscar', '').strip()
    filtro = request.args.get('filtro', 'Todos')
    categoria_filtro = request.args.get('categoria', 'Todas las categorías')

    cur = mysql.connection.cursor()

    sql = """
        SELECT id, tipo, descripcion, monto, categoria, fecha
        FROM movimientos
        WHERE usuario_id = %s
    """

    valores = [usuario_id]

    if buscar:
        sql += " AND (descripcion LIKE %s OR categoria LIKE %s)"
        valores.append('%' + buscar + '%')
        valores.append('%' + buscar + '%')

    if filtro in ['Ingreso', 'Gasto']:
        sql += " AND tipo = %s"
        valores.append(filtro)

    if categoria_filtro and categoria_filtro != 'Todas las categorías':
        sql += " AND categoria = %s"
        valores.append(categoria_filtro)

    sql += " ORDER BY fecha DESC, id DESC"

    cur.execute(sql, valores)
    rows = cur.fetchall()

    movimientos_lista = []

    for id_mov, tipo, descripcion, monto, categoria, fecha in rows:
        icono, _ = categoria_meta(categoria)

        movimientos_lista.append({
            "id": id_mov,
            "tipo": tipo,
            "descripcion": descripcion,
            "monto": float(monto or 0),
            "categoria": categoria or "Sin categoría",
            "icono": icono,
            "fecha": fecha.strftime("%d/%m/%Y") if fecha else ""
        })

    cur.execute("""
        SELECT DISTINCT categoria
        FROM movimientos
        WHERE usuario_id = %s
          AND categoria IS NOT NULL
          AND categoria != ''
        ORDER BY categoria ASC
    """, (usuario_id,))

    categorias = [fila[0] for fila in cur.fetchall()]

    return render_template(
        'movimientos.html',
        usuario=session.get('usuario', 'Usuario'),
        correo_usuario=session.get('correo', ''),
        datos=movimientos_lista,
        buscar=buscar,
        filtro=filtro,
        categoria_filtro=categoria_filtro,
        categorias=categorias,
        hoy_input=datetime.now().strftime('%Y-%m-%d')
    )

#GUARDAR MOVIMIENTOS
@app.route('/guardar_movimiento', methods=['POST'])
def guardar_movimiento():
    if 'usuario_id' not in session: 
        return redirect('/')

    tipo = request.form.get('tipo', 'Ingreso')
    descripcion = request.form.get('descripcion', '').strip()
    monto = request.form.get('monto', '0')
    categoria = request.form.get('categoria', 'Sin categoría')
    fecha = request.form.get('fecha', '')
    redirect_to = request.form.get('redirect_to', 'dashboard')

    try:
        monto = float(monto)
    except:
        monto = 0

    if not descripcion or monto <= 0:
        flash('Completa correctamente la descripción y el monto.', 'error')

        if redirect_to == 'movimientos':
            return redirect('/movimientos')

        return redirect('/dashboard')

    cur = mysql.connection.cursor()

    fecha_guardar = fecha if fecha else datetime.now().strftime('%Y-%m-%d')

    cur.execute("""
        INSERT INTO movimientos
        (usuario_id, tipo, descripcion, monto, categoria, fecha)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        session['usuario_id'],
        tipo,
        descripcion,
        monto,
        categoria,
        fecha_guardar
    ))

    mysql.connection.commit()

    flash('Movimiento guardado correctamente.', 'success')

    if redirect_to == 'movimientos':
        return redirect('/movimientos')

    return redirect('/dashboard')

#Eliminar id
@app.route('/eliminar/<int:id>')
def eliminar(id):
    if 'usuario_id' not in session:
        return redirect('/')

    cur = mysql.connection.cursor()

    cur.execute(
        "DELETE FROM movimientos WHERE id = %s AND usuario_id = %s",
        (id, session['usuario_id'])
    )

    mysql.connection.commit()

    flash('Movimiento eliminado correctamente.', 'success')
    return redirect('/movimientos')

#Categorias 
@app.route('/categorias')
def categorias():
    if 'usuario_id' not in session:
        return redirect('/')

    usuario_id = session['usuario_id']

    cur = mysql.connection.cursor()

    # Gasto total del mes
    cur.execute("""
        SELECT IFNULL(SUM(monto), 0)
        FROM movimientos
        WHERE usuario_id = %s
          AND tipo = 'Gasto'
          AND MONTH(fecha) = MONTH(CURDATE())
          AND YEAR(fecha) = YEAR(CURDATE())
    """, (usuario_id,))
    total_gastos = float(cur.fetchone()[0] or 0)

    # Gastos agrupados por categoría del mes
    cur.execute("""
        SELECT categoria, IFNULL(SUM(monto), 0) AS total
        FROM movimientos
        WHERE usuario_id = %s
          AND tipo = 'Gasto'
          AND MONTH(fecha) = MONTH(CURDATE())
          AND YEAR(fecha) = YEAR(CURDATE())
        GROUP BY categoria
        ORDER BY total DESC
    """, (usuario_id,))
    rows_gastos = cur.fetchall()

    # Presupuestos del usuario
    cur.execute("""
        SELECT categoria, limite_mensual
        FROM presupuestos
        WHERE usuario_id = %s
    """, (usuario_id,))
    rows_presupuestos = cur.fetchall()

    presupuestos_map = {
        str(categoria).strip().lower(): float(limite or 0)
        for categoria, limite in rows_presupuestos
    }

    categorias_base = [
        "Alimentación",
        "Transporte",
        "Vivienda",
        "Salud",
        "Educación",
        "Ocio",
        "Ropa",
        "Otros"
    ]

    gastos_map = {
        str(categoria or "Otros").strip(): float(total or 0)
        for categoria, total in rows_gastos
    }

    categorias_reporte = []

    for nombre in categorias_base:
        total = gastos_map.get(nombre, 0)

        # Por si en BD está sin tilde
        if nombre == "Alimentación":
            total += gastos_map.get("Alimentacion", 0)

        if nombre == "Educación":
            total += gastos_map.get("Educacion", 0)

        porcentaje = 0
        if total_gastos > 0:
            porcentaje = round((total / total_gastos) * 100, 1)

        icono, color = categoria_meta(nombre)

        presupuesto = presupuestos_map.get(nombre.lower(), 0)

        porcentaje_presupuesto = 0
        if presupuesto > 0:
            porcentaje_presupuesto = round((total / presupuesto) * 100, 1)
        elif total_gastos > 0:
            porcentaje_presupuesto = porcentaje

        categorias_reporte.append({
            "nombre": nombre,
            "icono": icono,
            "color": color,
            "total": total,
            "porcentaje": porcentaje,
            "presupuesto": presupuesto,
            "barra": min(porcentaje_presupuesto, 100)
        })

    categorias_detalle = [
        item for item in categorias_reporte
        if item["total"] > 0
    ]

    return render_template(
        'categorias.html',
        usuario=session.get('usuario', 'Usuario'),
        correo_usuario=session.get('correo', ''),
        categorias_reporte=categorias_reporte,
        categorias_detalle=categorias_detalle,
        total_gastos=total_gastos
    )

#ALERTAS
@app.route('/alertas')
def alertas():
    if 'usuario_id' not in session:
        return redirect('/')

    usuario_id = session['usuario_id']
    cur = mysql.connection.cursor()

    categorias_base = [
    "Alimentación",
    "Transporte",
    "Vivienda",
    "Salud",
    "Educación",
    "Ocio",
    "Ropa",
    "Hogar",
    "Servicios",
    "Otros"
    ]

    # Gastos del mes por categoría
    cur.execute("""
        SELECT categoria, IFNULL(SUM(monto), 0)
        FROM movimientos
        WHERE usuario_id = %s
          AND tipo = 'Gasto'
          AND MONTH(fecha) = MONTH(CURDATE())
          AND YEAR(fecha) = YEAR(CURDATE())
        GROUP BY categoria
    """, (usuario_id,))

    gastos_rows = cur.fetchall()

    gastos_map = {
        str(categoria or '').strip().lower(): float(total or 0)
        for categoria, total in gastos_rows
    }

    # Presupuestos configurados por usuario
    cur.execute("""
        SELECT categoria, limite_mensual
        FROM presupuestos
        WHERE usuario_id = %s
    """, (usuario_id,))

    presupuestos_rows = cur.fetchall()

    presupuestos_map = {
        str(categoria or '').strip().lower(): float(limite or 0)
        for categoria, limite in presupuestos_rows
    }

    alertas_lista = []

    for categoria in categorias_base:
        key = categoria.strip().lower()

        gasto = gastos_map.get(key, 0)

        # Compatibilidad por si guardaste sin tilde
        if key == "alimentación":
            gasto += gastos_map.get("alimentacion", 0)

        if key == "educación":
            gasto += gastos_map.get("educacion", 0)

        limite = presupuestos_map.get(key, 0)

        if key == "alimentación":
            limite = limite or presupuestos_map.get("alimentacion", 0)

        if key == "educación":
            limite = limite or presupuestos_map.get("educacion", 0)

        porcentaje = 0

        if limite > 0:
            porcentaje = round((gasto / limite) * 100)

        porcentaje_barra = min(porcentaje, 100)

        if limite <= 0:
            estado = "sin_presupuesto"
            estado_texto = "Sin presupuesto configurado"
            alerta_clase = "budget-neutral"
            icono_estado = "ℹ️"
            barra_clase = "neutral"
        elif porcentaje >= 100:
            estado = "superado"
            estado_texto = "Límite superado"
            alerta_clase = "budget-danger"
            icono_estado = "🚨"
            barra_clase = "danger"
        elif porcentaje >= 80:
            estado = "cerca"
            estado_texto = "Cerca del límite"
            alerta_clase = "budget-warning"
            icono_estado = "⚠️"
            barra_clase = "warning"
        else:
            estado = "ok"
            estado_texto = "Dentro del presupuesto"
            alerta_clase = "budget-ok"
            icono_estado = "✅"
            barra_clase = "ok"

        icono_categoria, _ = categoria_meta(categoria)

        alertas_lista.append({
            "categoria": categoria,
            "icono_categoria": icono_categoria,
            "gasto": gasto,
            "limite": limite,
            "porcentaje": porcentaje,
            "porcentaje_barra": porcentaje_barra,
            "estado": estado,
            "estado_texto": estado_texto,
            "alerta_clase": alerta_clase,
            "icono_estado": icono_estado,
            "barra_clase": barra_clase
        })

    # Orden: primero superadas/cerca del límite, luego normales
    prioridad = {
        "superado": 1,
        "cerca": 2,
        "ok": 3,
        "sin_presupuesto": 4
    }

    alertas_lista.sort(key=lambda item: prioridad[item["estado"]])

    return render_template(
        'alertas.html',
        usuario=session.get('usuario', 'Usuario'),
        correo_usuario=session.get('correo', ''),
        alertas=alertas_lista
    )

#Guardar presupuesto
@app.route('/guardar_presupuesto', methods=['POST'])
def guardar_presupuesto():
    if 'usuario_id' not in session:
        return redirect('/')

    usuario_id = session['usuario_id']
    categoria = request.form.get('categoria', '').strip()
    limite = request.form.get('limite', '0')

    try:
        limite = float(limite)
    except:
        limite = 0

    if not categoria or limite <= 0:
        flash('Completa correctamente la categoría y el límite.', 'error')
        return redirect('/alertas')

    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT id
        FROM presupuestos
        WHERE usuario_id = %s
          AND LOWER(TRIM(categoria)) = LOWER(TRIM(%s))
        LIMIT 1
    """, (usuario_id, categoria))

    presupuesto_existente = cur.fetchone()

    if presupuesto_existente:
        cur.execute("""
            UPDATE presupuestos
            SET limite_mensual = %s
            WHERE id = %s
              AND usuario_id = %s
        """, (limite, presupuesto_existente[0], usuario_id))
    else:
        cur.execute("""
            INSERT INTO presupuestos(usuario_id, categoria, limite_mensual)
            VALUES(%s, %s, %s)
        """, (usuario_id, categoria, limite))

    mysql.connection.commit()

    flash('Presupuesto guardado correctamente.', 'success')
    return redirect('/alertas')


# CERRAR SESION
@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada correctamente.', 'success')
    return redirect('/') 
if __name__ == "__main__":
    app.run(debug=True, port=5000)
