import mysql.connector
from mysql.connector import Error
from flask_bcrypt import check_password_hash as bcrypt_check_password_hash 
import os
from dotenv import load_dotenv

load_dotenv()

class Database:
    def __init__(self):
        self.host = os.getenv('DB_HOST')
        self.user = os.getenv('DB_USER')
        self.password = os.getenv('DB_PASSWORD')
        self.database = os.getenv('DB_NAME')
        self.connection = None
        self._connect() # Intentar conectar al inicializar

    def _connect(self):
        """Establece o restablece la conexión a la base de datos."""
        try:
            # Desconectar si ya existe una conexión para evitar múltiples conexiones abiertas
            if self.connection and self.connection.is_connected():
                self.connection.close()

            self.connection = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                connection_timeout=10 
            )
            if self.connection.is_connected():
                print("✅ Conexión exitosa a la base de datos")
            else:
                self.connection = None 
                print("🔌 La conexión no se pudo activar después de mysql.connector.connect.")
        except Error as e:
            print(f"❌ Error al conectar a la base de datos: {e}")
            self.connection = None 

    def disconnect(self):
        """Cierra la conexión activa."""
        if self.connection and self.connection.is_connected():
            try:
                self.connection.close()
                print("🔌 Conexión cerrada")
            except Error as e:
                print(f"❌ Error al cerrar la conexión: {e}")
            finally:
                self.connection = None # Siempre marcar como None después de intentar cerrar

    def _ensure_connection(self):
        """Asegura que haya una conexión activa, reconectando si es necesario."""
        try:
            if not self.connection or not self.connection.is_connected():
                print("🔌 Conexión perdida o no establecida. Intentando reconectar...")
                self._connect()
            
            # Verificar de nuevo después del intento de conexión
            if not self.connection or not self.connection.is_connected():
                print("❌ Fallo crítico: No se pudo establecer la conexión a la base de datos después del intento.")
                return False
            return True
        except Exception as e: # Captura errores más amplios durante el chequeo/reconexión
            print(f"❌ Excepción en _ensure_connection: {e}")
            self.connection = None # Asegurar que la conexión sea None
            return False

    def execute_query(self, query, params=None):
        """Ejecuta consultas de escritura (INSERT/UPDATE/DELETE)."""
        if not self._ensure_connection():
            print("❌ execute_query falló: No hay conexión a la base de datos.")
            return False

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, params)
                self.connection.commit()
                return True
        except mysql.connector.Error as e: # Ser específico con el tipo de error
            print(f"❌ Error de MySQL en execute_query: {e}")
            if self.connection and self.connection.is_connected():
                try:
                    self.connection.rollback()
                    print("⏪ Rollback realizado.")
                except Error as rb_error:
                    print(f"❌ Error durante el rollback: {rb_error}")
            
            # Errores que típicamente significan que la conexión está rota
            if e.errno == 2006 or e.errno == 2013: 
                print("🔌 Conexión perdida detectada en execute_query. Desconectando.")
                self.disconnect()
            return False
        except Exception as e: # Otros errores inesperados
            print(f"❌ Error inesperado en execute_query: {e}")
            return False

    def fetch_query(self, query, params=None):
        """Ejecuta consultas de lectura (SELECT)."""
        if not self._ensure_connection():
            print("❌ fetch_query falló: No hay conexión a la base de datos.")
            return None

        try:
            with self.connection.cursor(dictionary=True) as cursor:
                cursor.execute(query, params)
                return cursor.fetchall()
        except mysql.connector.Error as e: # Ser específico con el tipo de error
            print(f"❌ Error de MySQL en fetch_query: {e}")
            if e.errno == 2006 or e.errno == 2013: # MySQL server has gone away / Lost connection
                print("🔌 Conexión perdida detectada en fetch_query. Desconectando.")
                self.disconnect()
            return None
        except Exception as e: # Otros errores inesperados
            print(f"❌ Error inesperado en fetch_query: {e}")
            return None

    def verificar_usuario(self, usuario, clave_plana):
        """Verifica si el usuario existe y valida la contraseña."""
        query = "SELECT id, usuario, clave FROM usuarios WHERE usuario = %s"
        # fetch_query se encarga de la conexión
        user_data_list = self.fetch_query(query, (usuario,))

        if user_data_list and len(user_data_list) > 0:
            usuario_db = user_data_list[0]
            clave_hasheada = usuario_db.get("clave")

            if clave_hasheada and bcrypt_check_password_hash(clave_hasheada, clave_plana):
                print("✅ Contraseña correcta")
                return usuario_db["id"]
            else:
                print("❌ Contraseña incorrecta para el usuario.")
        else:
            print("❌ Usuario no encontrado.")
        
        return None