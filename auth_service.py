"""Servicios de autenticación, bloqueo, recuperación y SMTP."""
from __future__ import annotations
import os, secrets, smtplib, mimetypes, ssl
from datetime import timedelta
from email.message import EmailMessage
from config_sistema import NOMBRE_SISTEMA, ahora_local, conectar_bd, obtener_configuracion, timestamp_local
from security import hash_password, verify_password

def _cfg(): return obtener_configuracion().get("seguridad", {})
def _log(cur, user_id, action, detail="", modulo="Seguridad"):
    """Registro compatible con bitácoras antiguas y Base v1."""
    cur.execute("INSERT INTO bitacora (id_usuario, accion, modulo, detalle, fecha) VALUES (%s,%s,%s,%s,%s)", (user_id, action, modulo, detail, timestamp_local()))


def registrar_evento(user_id, action, detail="", modulo="Sistema"):
    """Auditoría reutilizable; un fallo posterior no revierte la operación origen."""
    con = conectar_bd(False)
    if not con:
        return False
    cur = con.cursor()
    try:
        _log(cur, user_id, action, detail, modulo)
        con.commit()
        return True
    except Exception:
        con.rollback()
        return False
    finally:
        cur.close(); con.close()


def _registrar_recuperacion(user_id, accion, detalle):
    """Registra el resultado sin exponer códigos, contraseñas ni secretos."""
    con = conectar_bd(False)
    if not con:
        return
    cur = con.cursor()
    try:
        _log(cur, user_id, accion, detalle)
        con.commit()
    except Exception:
        con.rollback()
    finally:
        cur.close(); con.close()

def requiere_configuracion_inicial():
    """Inicializa SQLite mediante la capa central y detecta una tabla usuarios vacía."""
    con = conectar_bd(False)
    if not con:
        return False
    cur = con.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM usuarios")
        return int(cur.fetchone()[0] or 0) == 0
    except Exception:
        return False
    finally:
        cur.close(); con.close()

def crear_primer_administrador(nombre, username, correo, password, confirmar):
    """Crea el único usuario inicial sin credenciales predeterminadas."""
    nombre, username, correo = nombre.strip(), username.strip(), correo.strip().lower()
    if not nombre or not username or not correo or "@" not in correo:
        return False, "Completa nombre, usuario y correo válido."
    if not password or password != confirmar:
        return False, "Las contraseñas no coinciden."
    if len(password) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres."
    con = conectar_bd(False)
    if not con:
        return False, "No fue posible preparar la base de datos."
    cur = con.cursor(dictionary=True)
    try:
        con.start_transaction()
        cur.execute("SELECT COUNT(*) AS total FROM usuarios")
        if int(cur.fetchone()["total"] or 0) > 0:
            con.rollback()
            return False, "Ya existe un usuario. Inicia sesión normalmente."
        cur.execute("SELECT id FROM usuarios WHERE username=%s LIMIT 1", (username,))
        if cur.fetchone():
            con.rollback()
            return False, "Ese nombre de usuario ya está registrado."
        cur.execute("INSERT INTO usuarios (username,nombre_completo,correo,rol,estado,password) VALUES (%s,%s,%s,%s,%s,%s)", (username, nombre, correo, "Administrador", "Activo", hash_password(password)))
        user_id = cur.lastrowid
        try:
            _log(cur, user_id, "PRIMER_ADMINISTRADOR_CREADO", "Configuración inicial")
        except Exception:
            # No se impide la instalación si una base MySQL antigua aún no tiene bitácora.
            pass
        con.commit()
        return True, "Administrador creado correctamente. Ahora puedes iniciar sesión."
    except Exception:
        con.rollback()
        return False, "No fue posible crear el administrador. Verifica los datos e inténtalo nuevamente."
    finally:
        cur.close(); con.close()
def autenticar(username, password):
    con=conectar_bd(False); cur=con.cursor(dictionary=True)
    try:
        cur.execute("SELECT id,id_empleado,username,nombre_completo,correo,rol,estado,password,bloqueado_hasta,intentos_fallidos FROM usuarios WHERE username=%s LIMIT 1", (username,)); user=cur.fetchone()
        generic=(False,"No fue posible iniciar sesión. Verifica tus datos e inténtalo nuevamente.",None)
        if not user: return generic
        now=ahora_local(); blocked=user.get("bloqueado_hasta")
        if blocked and str(blocked) > now.strftime("%Y-%m-%d %H:%M:%S"): return False,"Tu cuenta está bloqueada temporalmente. Intenta más tarde.",None
        valid, upgrade=verify_password(password,user["password"])
        if not valid:
            attempts=int(user.get("intentos_fallidos") or 0)+1; limit=int(_cfg().get("max_intentos_login",5))
            lock=(now+timedelta(minutes=int(_cfg().get("bloqueo_minutos",15)))).strftime("%Y-%m-%d %H:%M:%S") if attempts>=limit else None
            cur.execute("UPDATE usuarios SET intentos_fallidos=%s,bloqueado_hasta=%s WHERE id=%s",(0 if lock else attempts,lock,user["id"])); _log(cur,user["id"],"LOGIN_FALLIDO","Bloqueo temporal" if lock else "Contraseña incorrecta"); con.commit(); return generic
        if str(user["estado"]).lower()!="activo": return False,"Tu usuario se encuentra inactivo. Consulta con un administrador.",None
        if upgrade: cur.execute("UPDATE usuarios SET password=%s WHERE id=%s",(hash_password(password),user["id"]))
        cur.execute("UPDATE usuarios SET ultimo_acceso=%s,intentos_fallidos=0,bloqueado_hasta=NULL WHERE id=%s",(timestamp_local(),user["id"])); _log(cur,user["id"],"LOGIN_EXITOSO","Inicio de sesión"); con.commit(); return True,"",user
    finally: cur.close(); con.close()
def solicitar_codigo(identificador, entregar=True):
    """Genera un código para correo o usuario, sin enumerar cuentas desde la UI."""
    identificador = (identificador or "").strip()
    con=conectar_bd(False); cur=con.cursor(dictionary=True)
    try:
        cur.execute("SELECT id,nombre_completo,correo FROM usuarios WHERE (correo=%s OR username=%s) AND estado='Activo' LIMIT 1",(identificador, identificador)); user=cur.fetchone()
        if not user:
            return True,"Si los datos corresponden a una cuenta registrada, se enviará un código de recuperación.",None
        cur.execute("UPDATE password_reset_codes SET usado=1 WHERE id_usuario=%s AND usado=0",(user["id"],)); code=f"{secrets.randbelow(1_000_000):06d}"; expiry=ahora_local()+timedelta(minutes=int(_cfg().get("codigo_expira_minutos",10)))
        cur.execute("INSERT INTO password_reset_codes (id_usuario,codigo_hash,expira_en,intentos_maximos,creado_en) VALUES (%s,%s,%s,%s,%s)", (user["id"], hash_password(code), expiry.strftime("%Y-%m-%d %H:%M:%S"), int(_cfg().get("max_intentos_codigo", 5)), timestamp_local()))
        codigo_id = cur.lastrowid
        _log(cur, user["id"], "RECUPERACION_SOLICITADA", "Código generado")
        con.commit()
        if entregar:
            enviado, mensaje, _ = enviar_codigo(user["correo"],user["nombre_completo"],code)
            if not enviado:
                # Un código cuyo correo no pudo entregarse no queda utilizable
                # ni acumulado en la base; nunca se simula un envío exitoso.
                cur.execute("UPDATE password_reset_codes SET usado=1 WHERE id=%s", (codigo_id,))
                con.commit()
            _registrar_recuperacion(user["id"], "RECUPERACION_CODIGO_ENVIADO" if enviado else "RECUPERACION_ENVIO_FALLIDO", "Correo de recuperación enviado" if enviado else "No fue posible enviar el correo de recuperación")
            return enviado, mensaje, None
        return True,"Código generado para prueba.",code
    finally: cur.close(); con.close()
def validar_y_restaurar(identificador,codigo,nueva):
    if len(nueva)<8: return False,"La nueva contraseña debe tener al menos 8 caracteres."
    if not str(codigo).isdigit() or len(str(codigo)) != 6:
        return False,"Ingresa el código de recuperación de 6 dígitos."
    con=conectar_bd(False); cur=con.cursor(dictionary=True)
    try:
        cur.execute("SELECT u.id,u.password,r.id AS rid,r.codigo_hash,r.expira_en,r.intentos,r.intentos_maximos FROM usuarios u JOIN password_reset_codes r ON r.id_usuario=u.id WHERE (u.correo=%s OR u.username=%s) AND r.usado=0 ORDER BY r.id DESC LIMIT 1",(identificador, identificador)); row=cur.fetchone()
        if not row: return False,"Código inválido o ya utilizado."
        if str(row["expira_en"]) < timestamp_local() or int(row["intentos"])>=int(row["intentos_maximos"]):
            cur.execute("UPDATE password_reset_codes SET usado=1 WHERE id=%s", (row["rid"],)); _log(cur,row["id"],"RECUPERACION_CODIGO_INVALIDADO","Código expirado o intentos agotados"); con.commit()
            return False,"El código expiró o agotó sus intentos. Solicita uno nuevo."
        valid,_=verify_password(codigo,row["codigo_hash"])
        if not valid:
            intentos = int(row["intentos"] or 0) + 1
            agotado = intentos >= int(row["intentos_maximos"])
            cur.execute("UPDATE password_reset_codes SET intentos=%s, usado=%s WHERE id=%s",(intentos, 1 if agotado else 0, row["rid"]));
            if agotado: _log(cur,row["id"],"RECUPERACION_CODIGO_INVALIDADO","Máximo de intentos agotado")
            con.commit(); return False,"El código agotó sus intentos. Solicita uno nuevo." if agotado else "Código incorrecto."
        cur.execute("UPDATE usuarios SET password=%s,intentos_fallidos=0,bloqueado_hasta=NULL WHERE id=%s",(hash_password(nueva),row["id"])); cur.execute("UPDATE password_reset_codes SET usado=1 WHERE id=%s",(row["rid"],)); _log(cur,row["id"],"CONTRASENA_RESTABLECIDA","Recuperación confirmada"); con.commit(); return True,"Contraseña actualizada correctamente."
    finally: cur.close(); con.close()
def enviar_correo(destino, asunto, contenido, adjuntos=None):
    """Envía correo con la única configuración SMTP central del sistema.

    Las credenciales siempre se leen de variables de entorno; los adjuntos son
    rutas temporales y nunca se guardan en la base de datos ni en configuración.
    """
    smtp = obtener_configuracion().get("correo_smtp", {})
    host = smtp.get("servidor") or os.getenv("GRUPO_JE_SMTP_HOST")
    user = os.getenv("GRUPO_JE_SMTP_USER") or smtp.get("usuario") or smtp.get("remitente", "")
    password = os.getenv("GRUPO_JE_SMTP_PASSWORD")
    if not host or not user or not password:
        return False, "SMTP no configurado. Define GRUPO_JE_SMTP_HOST, GRUPO_JE_SMTP_USER y GRUPO_JE_SMTP_PASSWORD.", None
    try:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = asunto, user, destino
        msg.set_content(contenido)
        for ruta in adjuntos or ():
            with open(ruta, "rb") as archivo:
                datos = archivo.read()
            tipo, _ = mimetypes.guess_type(ruta)
            principal, secundario = (tipo or "application/octet-stream").split("/", 1)
            msg.add_attachment(datos, maintype=principal, subtype=secundario, filename=os.path.basename(ruta))
        cliente = smtplib.SMTP_SSL if smtp.get("ssl", False) else smtplib.SMTP
        with cliente(host, int(smtp.get("puerto", 465 if smtp.get("ssl", False) else 587)), timeout=12) as server:
            if smtp.get("tls", True) and not smtp.get("ssl", False): server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return True, "Correo enviado correctamente.", None
    except FileNotFoundError:
        return False, "No fue posible generar el archivo adjunto de la factura.", None
    except smtplib.SMTPAuthenticationError:
        return False, "No fue posible autenticar el correo SMTP. Verifica las credenciales seguras.", None
    except smtplib.SMTPRecipientsRefused:
        return False, "El servidor rechazó la dirección de correo destinataria.", None
    except (smtplib.SMTPNotSupportedError, ssl.SSLError):
        return False, "La seguridad TLS/SSL no coincide con la configuración del servidor SMTP.", None
    except smtplib.SMTPServerDisconnected:
        return False, "El servidor SMTP cerró la conexión. Verifica puerto y seguridad TLS/SSL.", None
    except ValueError:
        return False, "El puerto SMTP configurado no es válido.", None
    except (smtplib.SMTPConnectError, TimeoutError, OSError):
        return False, "No fue posible conectar con el servidor SMTP.", None
    except smtplib.SMTPException:
        return False, "No fue posible enviar el correo. Revisa la configuración SMTP.", None
    except Exception:
        return False, "No fue posible preparar el correo para su envío.", None


def enviar_codigo(destino,nombre,codigo):
    contenido = f"Hola, {nombre}.\n\nRecibimos una solicitud para restablecer la contraseña de tu cuenta de Grupo JE.\n\nTu código de verificación es:\n\n{codigo}\n\nEste código vence en {_cfg().get('codigo_expira_minutos',10)} minutos.\n\nSi tú no solicitaste este cambio, puedes ignorar este mensaje.\n\nPor seguridad, nunca compartas este código con nadie.\n\nGrupo JE\n{NOMBRE_SISTEMA}"
    enviado, mensaje, detalle = enviar_correo(destino, "Grupo JE — Código para recuperar tu contraseña", contenido)
    return enviado, ("Código enviado al correo registrado." if enviado else mensaje), detalle

def cambiar_contrasena(user_id, actual, nueva, confirmar):
    if not nueva or nueva != confirmar: return False,"Las nuevas contraseñas no coinciden."
    if len(nueva) < 8: return False,"La nueva contraseña debe tener al menos 8 caracteres."
    con=conectar_bd(False); cur=con.cursor(dictionary=True)
    try:
        cur.execute("SELECT password FROM usuarios WHERE id=%s",(user_id,)); row=cur.fetchone()
        if not row or not verify_password(actual,row["password"])[0]: return False,"La contraseña actual es incorrecta."
        cur.execute("UPDATE usuarios SET password=%s WHERE id=%s",(hash_password(nueva),user_id)); _log(cur,user_id,"CONTRASENA_CAMBIADA","Cambio desde perfil"); con.commit(); return True,"Contraseña actualizada correctamente."
    finally: cur.close(); con.close()

def actualizar_perfil(user_id, nombre, correo):
    if not nombre.strip() or "@" not in correo: return False,"Ingresa nombre y correo válidos."
    con=conectar_bd(False); cur=con.cursor()
    try:
        cur.execute("UPDATE usuarios SET nombre_completo=%s, correo=%s WHERE id=%s",(nombre.strip(),correo.strip(),user_id)); _log(cur,user_id,"PERFIL_ACTUALIZADO","Datos de contacto"); con.commit(); return True,"Perfil actualizado."
    except Exception: con.rollback(); return False,"No se pudo actualizar el perfil. Verifica que el correo no esté duplicado."
    finally: cur.close(); con.close()
