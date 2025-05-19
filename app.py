from flask import Flask, render_template, request, redirect, url_for, session, flash
from conexion import Database
import os
import shutil  # Para eliminar carpetas y archivos
from functools import wraps
from flask_bcrypt import Bcrypt
from flask_session import Session
from dotenv import load_dotenv
from datetime import datetime
from email.mime.text import MIMEText
from smtplib import SMTP
from math import ceil



# Cargar variables de entorno
load_dotenv()

# Inicialización de la aplicación Flask
app = Flask(__name__)
bcrypt = Bcrypt(app)
app.config['DEBUG'] = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

# Configuración de la sesión
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

@app.template_filter('miles')
def miles_filter(value):
    try:
        # Convertir a entero y formatear con comas
        formateado = f"{int(value):,}"
        # Reemplazar comas por puntos
        return formateado.replace(",", ".")
    except:
        # Si falla (por ej., no es número), regresamos el valor original
        return value


# Instancia de la base de datos
db = Database()

# Decorador para proteger rutas
def login_requerido(f):
    @wraps(f)
    def decorador(*args, **kwargs):
        if 'usuario_id' not in session:
            flash("Debes iniciar sesión para acceder a esta página", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorador

# Context Processor para que 'session' esté disponible en todas las plantillas
@app.context_processor
def inject_session():
    return dict(session=session)

# Configuración de la carpeta para guardar imágenes (usando app.root_path)
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'img')

# Crear el directorio si no existe
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

### --- RUTAS PÚBLICAS --- ###
@app.route('/')
def index():
    # Consulta SQL para obtener los 4 vehículos más recientes
    query_ultimas_publicaciones = """
                                SELECT 
                                    v.patente, 
                                    v.marca, 
                                    v.modelo, 
                                    v.año, 
                                    v.precio, 
                                    v.fecha_adquisicion, 
                                    v.descripcion, 
                                    i.ruta AS img
                                FROM 
                                    vehiculos v
                                LEFT JOIN 
                                    imagenes i ON v.patente = i.patente
                                GROUP BY 
                                    v.patente, v.marca, v.modelo, v.año, v.precio, v.fecha_adquisicion, v.descripcion
                                ORDER BY 
                                    v.fecha_adquisicion DESC
                                LIMIT 4
                                """
    ultimas_publicaciones = db.fetch_query(query_ultimas_publicaciones)
    
        # Consulta para contar los vehículos disponibles
    query_stock_disponible = "SELECT COUNT(*) AS total FROM vehiculos;"
    resultado_stock = db.fetch_query(query_stock_disponible)

    # Extraer el número total de vehículos disponibles
    total_vehiculos = resultado_stock[0]['total'] if resultado_stock else 0

    return render_template('home.html', 
                           active_page='index', 
                           ultimas_publicaciones=ultimas_publicaciones,
                           total_vehiculos=total_vehiculos)



@app.route('/vehiculos')
def vehiculos():
    # 1) Tomar parámetro de página (si no existe, usar 1)
    page = request.args.get('page', default=1, type=int)
    
    # 2) Definir cuántos vehículos mostrar por página
    per_page = 6
    
    # 3) Calcular desde qué registro empezar
    offset = (page - 1) * per_page

    # 4) Consultar cuántos vehículos hay en total
    query_count = "SELECT COUNT(*) AS total FROM vehiculos"
    result_count = db.fetch_query(query_count)
    total_vehiculos = result_count[0]['total'] if result_count else 0
    
    # 5) Consultar los vehículos de la página actual
    #    Ajusta la consulta a tus necesidades (LEFT JOIN, ORDER, etc.)
    query_vehiculos = """
        SELECT v.patente, v.marca, v.modelo, v.año, v.precio, v.estado,
               (SELECT ruta FROM imagenes WHERE imagenes.patente = v.patente LIMIT 1) AS img
        FROM vehiculos v
        ORDER BY v.fecha_adquisicion DESC
        LIMIT %s OFFSET %s
    """
    autos = db.fetch_query(query_vehiculos, (per_page, offset))

    # 6) Calcular cuántas páginas en total
    total_pages = ceil(total_vehiculos / per_page)

    # 7) Si aún quieres mostrar "ultimas_publicaciones" (4 vehículos más recientes)
    query_ultimas_publicaciones = """
        SELECT v.patente, v.marca, v.modelo, v.año, v.precio, v.estado, v.descripcion,
               (SELECT ruta FROM imagenes WHERE imagenes.patente = v.patente LIMIT 1) AS img
        FROM vehiculos v
        ORDER BY v.fecha_adquisicion DESC
        LIMIT 4
    """
    ultimas_publicaciones = db.fetch_query(query_ultimas_publicaciones)

    # 8) Renderizar la plantilla pasando los datos necesarios
    return render_template(
        'vehiculos.html',
        autos=autos,
        ultimas_publicaciones=ultimas_publicaciones,
        active_page='vehiculos',
        page=page,
        total_pages=total_pages
    )



@app.route('/vehiculo/<string:patente>')
def vehiculo(patente):
    """Muestra la información de un vehículo específico."""
    query_vehiculo = "SELECT * FROM vehiculos WHERE patente = %s"
    query_imagenes = "SELECT ruta FROM imagenes WHERE patente = %s"

    vehiculo = db.fetch_query(query_vehiculo, (patente,))
    imagenes = db.fetch_query(query_imagenes, (patente,))

    if not vehiculo:
        return "Vehículo no encontrado", 404

    return render_template('vehiculo.html', vehiculo=vehiculo[0], imagenes=imagenes)

@app.route('/contacto', methods =['GET', 'POST'])
def contacto():
    if request.method == 'POST':
        nombre = request.form['name'] # Ahora funcionará porque agregamos 'name' en el template
        email = request.form['email']
        asunto = request.form['telefono']
        mensaje = request.form['message']

        # Configuración del correo
        remitente = os.getenv('EMAIL_USER') # Usa variable de entorno
        destinatario = os.getenv('EMAIL_RECIPIENT') # Usa variable de entorno
        asunto_correo = 'Nuevo mensaje de contacto: ' + asunto

        # Cuerpo del mensaje
        cuerpo = f"Nombre: {nombre}\nEmail: {email}\nTelefono: {asunto}\nMensaje: {mensaje}"

        # Envío del correo (usando smtplib)
        try:
            mensaje_email = MIMEText(cuerpo, 'plain', 'utf-8') # Especificar utf-8
            mensaje_email['Subject'] = asunto_correo
            mensaje_email['From'] = remitente
            mensaje_email['To'] = destinatario

            servidor_smtp = SMTP('smtp.gmail.com', 587)
            servidor_smtp.starttls()
            servidor_smtp.login(remitente, os.getenv('EMAIL_PASS')) # Usa variable de entorno para la contraseña

            servidor_smtp.sendmail(remitente, destinatario, mensaje_email.as_string())
            servidor_smtp.quit()

            flash('¡Gracias por tu mensaje! Ha sido enviado.', 'success')
        except Exception as e:
            # Imprimir el error para debugging (puedes usar logging en producción)
            print(f"Error al enviar el mensaje: {e}")
            flash(f"Error al enviar el mensaje: {str(e)}", 'danger')

    return render_template('contacto.html', active_page='contacto')

### --- RUTAS PROTEGIDAS --- ###
@app.route('/admin')
@login_requerido
def admin():
    """Panel de administración (requiere login)."""
    return render_template('admin.html', active_page='admin')


@app.route('/admin/agregar_vehiculo', methods=['GET', 'POST'])
@login_requerido
def guardar_vehiculo():
    """Permite agregar un vehículo al sistema."""
    if request.method == 'POST':
        patente = request.form.get('patente').strip()
        marca = request.form.get('marca').strip()
        modelo = request.form.get('modelo').strip()
        precio = request.form.get('precio').strip()
        año = request.form.get('año').strip()
        descripcion = request.form.get('descripcion').strip()
     
        combustible = request.form.get('combustible').strip()
        fecha_adquisicion = request.form.get('fecha_adquisicion').strip()
        estado = request.form.get('estado').strip()
        kilometraje = request.form.get('kilometraje').strip()
        imagenes = request.files.getlist('imagenes')

        if not all([patente, marca, modelo, precio, año, descripcion, combustible, fecha_adquisicion, estado, kilometraje ]):
            flash("Todos los campos son obligatorios.", "warning")
            return render_template('agregar_vehiculo.html')

        # Crear carpeta para el vehículo en static/img usando la patente
        carpeta = os.path.join(app.config['UPLOAD_FOLDER'], patente)
        os.makedirs(carpeta, exist_ok=True)

        try:
            query_vehiculo = """
                INSERT INTO vehiculos (patente, marca, modelo, precio, año, descripcion, combustible, fecha_adquisicion, estado, kilometraje)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            db.execute_query(query_vehiculo, (patente, marca, modelo, precio, año, descripcion,  combustible, fecha_adquisicion, estado, kilometraje))

            for imagen in imagenes:
                if imagen and imagen.filename:
                    # Se construye la ruta relativa para la BD y la ruta absoluta para guardar el archivo
                    ruta_relativa = os.path.join('img', patente, imagen.filename).replace('\\', '/')
                    ruta_absoluta = os.path.join(carpeta, imagen.filename)
                    imagen.save(ruta_absoluta)

                    query_imagen = "INSERT INTO imagenes (patente, ruta) VALUES (%s, %s)"
                    db.execute_query(query_imagen, (patente, ruta_relativa))

            flash("Vehículo agregado con éxito.", "success")
            return redirect(url_for('admin'))
        except Exception as e:
            flash(f"Error al agregar el vehículo: {str(e)}", "danger")

    return render_template('agregar_vehiculo.html', active_page='agregar_vehiculo')

@app.route('/admin/eliminar_vehiculo', methods=['GET', 'POST'])
@login_requerido
def eliminar_vehiculo():
    query_listar = "SELECT patente, modelo, marca, año, precio FROM vehiculos"
    vehiculos = db.fetch_query(query_listar) or [] 
    
    """Permite eliminar un vehículo."""
    if request.method == 'POST':
        patente = request.form.get('patente').strip()

        if not patente:
            flash("Debe ingresar una patente.", "warning")
            return render_template('eliminar_vehiculo.html')

        query_verificar = "SELECT * FROM vehiculos WHERE patente = %s"
        vehiculo = db.fetch_query(query_verificar, (patente,))

        if not vehiculo:
            flash("El vehículo no existe.", "danger")
            return render_template('eliminar_vehiculo.html', vehiculos = vehiculos)

        try:
            query_eliminar_imagenes = "DELETE FROM imagenes WHERE patente = %s"
            query_eliminar_vehiculo = "DELETE FROM vehiculos WHERE patente = %s"
            db.execute_query(query_eliminar_imagenes, (patente,))
            db.execute_query(query_eliminar_vehiculo, (patente,))

            # Se elimina la carpeta creada para el vehículo dentro de static/img
            carpeta_vehiculo = os.path.join(app.config['UPLOAD_FOLDER'], patente)
            shutil.rmtree(carpeta_vehiculo, ignore_errors=True)

            flash("Vehículo eliminado con éxito.", "success")
            return redirect(url_for('admin'))
        except Exception as e:
            flash(f"Error al eliminar el vehículo: {str(e)}", "danger")

    return render_template('eliminar_vehiculo.html', vehiculos = vehiculos)

@app.route('/admin/listar_vehiculos')
@login_requerido
def listar_vehiculos():
    """
    Muestra la lista de vehículos en el panel de administración,
    ordenados desde el más reciente al más antiguo según la fecha de adquisición.
    Obtiene una imagen por vehículo.
    """
    query = """
            SELECT 
                v.patente, 
                v.marca, 
                v.modelo, 
                v.precio, 
                v.estado, 
                v.fecha_adquisicion, 
                (SELECT i.ruta FROM imagenes i WHERE i.patente = v.patente LIMIT 1) AS img
            FROM 
                vehiculos v
            ORDER BY 
                v.fecha_adquisicion DESC
    """
    vehiculos = db.fetch_query(query)
    return render_template('listar_vehiculos.html', vehiculos=vehiculos, active_page='listar_vehiculos')

@app.route('/admin/cambiar_estado_vehiculo/<string:patente>', methods=['POST'])
@login_requerido
def cambiar_estado_vehiculo(patente):
    """Cambia el estado de un vehículo entre 'En Venta' y 'Vendido'."""
    nuevo_estado = request.form.get('nuevo_estado')

    if not nuevo_estado or nuevo_estado not in ['En Venta', 'Vendido']:
        flash("Estado no válido.", "danger")
        return redirect(url_for('listar_vehiculos'))

    try:
        # Verificar si el vehículo existe
        query_verificar = "SELECT patente FROM vehiculos WHERE patente = %s"
        vehiculo_existe = db.fetch_query(query_verificar, (patente,))

        if not vehiculo_existe:
            flash("Vehículo no encontrado.", "danger")
            return redirect(url_for('listar_vehiculos'))

        # Actualizar el estado del vehículo
        query_update = "UPDATE vehiculos SET estado = %s, fecha_modificacion = %s WHERE patente = %s"
        fecha_modificacion = datetime.now() # Asegúrate de importar datetime from datetime
        db.execute_query(query_update, (nuevo_estado, fecha_modificacion, patente))

        flash(f"El estado del vehículo {patente} ha sido actualizado a '{nuevo_estado}'.", "success")
    except Exception as e:
        flash(f"Error al cambiar el estado del vehículo: {str(e)}", "danger")

    return redirect(url_for('listar_vehiculos'))


@app.route('/admin/editar_vehiculo/<string:patente>', methods=['GET', 'POST'])
@login_requerido
def editar_vehiculo(patente):

    if request.method == 'POST':
        marca = request.form.get('marca', '').strip()
        modelo = request.form.get('modelo', '').strip()
        precio = request.form.get('precio', '').strip()
        año = request.form.get('año', '').strip()
        combustible = request.form.get('combustible', '').strip()
        fecha_adquisicion = request.form.get('fecha_adquisicion', '').strip()
        kilometraje = request.form.get('kilometraje', '').strip()
        estado = request.form.get('estado', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        nuevas_imagenes = request.files.getlist('imagenes')

        if not all([marca, modelo, precio, año, combustible,
                    fecha_adquisicion, kilometraje, estado, descripcion]):
            flash("Todos los campos son obligatorios.", "warning")
            return redirect(url_for('editar_vehiculo', patente=patente))

        try:
            fecha_modificacion = datetime.now()  # Obtiene la fecha y hora actuales

            query_update = """
                UPDATE vehiculos
                SET marca=%s, modelo=%s, precio=%s, año=%s,
                    combustible=%s, fecha_adquisicion=%s, kilometraje=%s, estado=%s, descripcion=%s,
                    fecha_modificacion=%s
                WHERE patente=%s
            """
            db.execute_query(query_update, (marca, modelo, precio, año, combustible,
                                            fecha_adquisicion, kilometraje, estado, descripcion, 
                                            fecha_modificacion, patente))

            # Crear carpeta para el vehículo si no existe
            carpeta = os.path.join(app.config['UPLOAD_FOLDER'], patente)
            os.makedirs(carpeta, exist_ok=True)

            # Guardar nuevas imágenes
            for imagen in nuevas_imagenes:
                if imagen and imagen.filename:
                    ruta_relativa = os.path.join('img', patente, imagen.filename).replace('\\', '/')
                    ruta_absoluta = os.path.join(carpeta, imagen.filename)
                    imagen.save(ruta_absoluta)

                    query_insert_imagen = "INSERT INTO imagenes (patente, ruta) VALUES (%s, %s)"
                    db.execute_query(query_insert_imagen, (patente, ruta_relativa))

            flash("Vehículo actualizado con éxito.", "success")
            return redirect(url_for('listar_vehiculos'))
        except Exception as e:
            flash(f"Error al actualizar el vehículo: {str(e)}", "danger")
            return redirect(url_for('editar_vehiculo', patente=patente))

    # GET: Obtener datos actuales del vehículo e imágenes asociadas
    query_vehiculo = "SELECT * FROM vehiculos WHERE patente = %s"
    vehiculo = db.fetch_query(query_vehiculo, (patente,))
    if not vehiculo:
        flash("Vehículo no encontrado.", "danger")
        return redirect(url_for('listar_vehiculos'))
    query_imagenes = "SELECT id, ruta FROM imagenes WHERE patente = %s"
    imagenes = db.fetch_query(query_imagenes, (patente,))
    return render_template('editar_vehiculo.html',
                           vehiculo=vehiculo[0],
                           imagenes=imagenes,
                           active_page='editar_vehiculo')


@app.route('/admin/eliminar_imagen/<int:id>', methods=['POST'])
@login_requerido
def eliminar_imagen(id):
    """
    Elimina una imagen específica del vehículo.
    Se elimina el archivo físico y se remueve el registro de la base de datos.
    """
    query_imagen = "SELECT patente, ruta FROM imagenes WHERE id = %s"
    imagen = db.fetch_query(query_imagen, (id,))
    if not imagen:
        flash("Imagen no encontrada.", "warning")
        return redirect(url_for('listar_vehiculos'))

    patente = imagen[0]['patente']
    # Usamos app.root_path para construir la ruta absoluta correcta
    ruta_imagen = os.path.join(app.root_path, 'static', imagen[0]['ruta'])
    try:
        if os.path.exists(ruta_imagen):
            os.remove(ruta_imagen)
        query_delete = "DELETE FROM imagenes WHERE id = %s"
        db.execute_query(query_delete, (id,))
        flash("Imagen eliminada con éxito.", "success")
    except Exception as e:
        flash(f"Error al eliminar la imagen: {str(e)}", "danger")

    return redirect(url_for('editar_vehiculo', patente=patente))



### --- AUTENTICACIÓN --- ###
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Manejo de autenticación de usuarios."""
    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip()
        clave = request.form.get('clave', '').strip()

        if not usuario or not clave:
            flash("Usuario y contraseña son obligatorios", "danger")
            return render_template('login.html')

        usuario_id = db.verificar_usuario(usuario, clave)
        if usuario_id:
            session['usuario_id'] = usuario_id
            session['usuario'] = usuario
            flash("Inicio de sesión exitoso", "success")
            return redirect(url_for('admin'))
        else:
            flash("Usuario o contraseña incorrectos", "danger")

    return render_template('login.html')

@app.route('/logout')
def logout():
    """Cierra la sesión del usuario."""
    session.clear()
    flash("Sesión cerrada correctamente", "info")
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=False)
