import os
import subprocess
import datetime
import threading
import time
import streamlit as st

PRIMARY_STREAM = "http://181.79.87.132:8000/play/a001/index.m3u8"
BACKUP_STREAM = "http://181.78.8.199:8000/play/a07l/index.m3u8"

RECORDINGS_DIR = "./temp_recordings"
LOG_FILE = "./recording_debug.log"
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# Control de estado en Streamlit
if "is_recording" not in st.session_state:
    st.session_state.is_recording = False
if "current_process" not in st.session_state:
    st.session_state.current_process = None

def write_log(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"
    print(log_entry, end="")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry)

def check_stream_working(url):
    write_log(f"Comprobando disponibilidad del stream: {url}")
    try:
        cmd = ["ffmpeg", "-y", "-timeout", "5000000", "-i", url, "-t", "1", "-f", "null", "-"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)
        if res.returncode == 0:
            write_log(f"Stream OK: {url}")
            return True
        else:
            write_log(f"Stream falló (code {res.returncode}): {url}")
            return False
    except Exception as e:
        write_log(f"Excepción al comprobar stream {url}: {str(e)}")
        return False

def start_recording(duracion_minutos):
    if st.session_state.is_recording:
        st.warning("⚠️ Ya hay una grabación en curso.")
        return
    
    write_log("Intentando iniciar nueva grabación...")
    stream_to_use = PRIMARY_STREAM if check_stream_working(PRIMARY_STREAM) else BACKUP_STREAM
    write_log(f"Stream seleccionado para grabar: {stream_to_use}")
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filepath = os.path.join(RECORDINGS_DIR, f"grabacion_{timestamp}.mp4")
    
    cmd = [
        "ffmpeg", "-y",
        "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
        "-i", stream_to_use,
        "-c:v", "copy", "-c:a", "aac",
        "-bsf:a", "aac_adtstoasc",
        output_filepath
    ]
    
    try:
        # Abrimos el proceso y redirigimos el stderr para capturar los logs de FFmpeg
        log_output = open(LOG_FILE, "a", encoding="utf-8")
        st.session_state.current_process = subprocess.Popen(cmd, stdout=log_output, stderr=log_output)
        st.session_state.is_recording = True
        write_log(f"🔴 Grabación iniciada. Guardando en: {output_filepath} por {duracion_minutos} min.")
        st.success(f"🔴 Grabación iniciada por {duracion_minutos} min.")
        
        duracion_segundos = duracion_minutos * 60
        def stop_after_timeout():
            time.sleep(duracion_segundos)
            stop_recording()

        threading.Thread(target=stop_after_timeout, daemon=True).start()
    except Exception as e:
        st.session_state.is_recording = False
        err_msg = f"⚠️ Error crítico al iniciar FFmpeg: {str(e)}"
        write_log(err_msg)
        st.error(err_msg)

def stop_recording():
    if not st.session_state.is_recording or st.session_state.current_process is None:
        write_log("Intento de detener grabación pero no hay ninguna activa.")
        return
    try:
        write_log("Deteniendo proceso de grabación...")
        st.session_state.current_process.terminate()
        st.session_state.current_process.wait(timeout=5)
        write_log("Proceso detenido correctamente.")
    except Exception as e:
        write_log(f"Fuerza bruta al matar proceso FFmpeg: {str(e)}")
        st.session_state.current_process.kill()
    finally:
        st.session_state.current_process = None
        st.session_state.is_recording = False
    st.info("⏹️ Grabación detenida y guardada correctamente.")

def convert_to_mp3(video_path):
    if not video_path or not os.path.exists(video_path):
        return None
    mp3_path = video_path.rsplit('.', 1)[0] + ".mp3"
    if os.path.exists(mp3_path):
        return mp3_path
    write_log(f"Convirtiendo a MP3: {video_path}")
    cmd = ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "libmp3lame", "-q:a", "2", mp3_path]
    try:
        subprocess.run(cmd, check=True)
        write_log("Conversión a MP3 exitosa.")
        return mp3_path
    except Exception as e:
        write_log(f"Error convirtiendo a MP3: {str(e)}")
        return None

def list_recordings():
    files = [f for f in os.listdir(RECORDINGS_DIR) if f.endswith('.mp4')]
    files.sort(reverse=True)
    return files

# Interfaz visual de Streamlit
st.set_page_config(page_title="Grabador Manual Streamlit", page_icon="🔴", layout="wide")

st.title("🔴 Grabador Manual de Streamings con Logs")
st.write("Panel de control con registro interno para verificar errores en tiempo real.")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Control de Grabación")
    duracion = st.slider("Duración de la grabación (Minutos):", min_value=5, max_value=180, value=60, step=5)
    
    if st.button("⚡ Iniciar Grabación", type="primary", use_container_width=True):
        start_recording(duracion)
        st.rerun()
        
    if st.button("🛑 Detener Inmediatamente", use_container_width=True):
        stop_recording()
        st.rerun()

    estado_actual = "🔴 Grabando en segundo plano..." if st.session_state.is_recording else "🟢 Sistema listo."
    st.info(f"**Estado:** {estado_actual}")

with col2:
    st.subheader("📁 Descargar a la PC")
    files = list_recordings()
    selected_file = st.selectbox("Seleccionar archivo guardado:", files if files else ["No hay grabaciones aún"])
    
    formato = st.radio("Formato de descarga:", ["Video (MP4)", "Audio (MP3)"], horizontal=True)
    
    if files and selected_file != "No hay grabaciones aún":
        path = os.path.join(RECORDINGS_DIR, selected_file)
        file_to_download = convert_to_mp3(path) if formato == "Audio (MP3)" else path
        
        if os.path.exists(file_to_download):
            with open(file_to_download, "rb") as f:
                st.download_button(
                    label=f"📥 Descargar {os.path.basename(file_to_download)} a tu PC",
                    data=f,
                    file_name=os.path.basename(file_to_download),
                    mime="video/mp4" if formato == "Video (MP4)" else "audio/mpeg",
                    use_container_width=True
                )
    
    if st.button("🗑️ Limpiar Servidor (Borrar Todo)", use_container_width=True):
        for f in os.listdir(RECORDINGS_DIR):
            file_path = os.path.join(RECORDINGS_DIR, f)
            if os.path.isfile(file_path):
                os.remove(file_path)
        write_log("Servidor limpiado por completo de grabaciones.")
        st.success("¡Espacio limpiado por completo!")
        st.rerun()

# Visor de Logs en vivo en la interfaz
st.subheader("📋 Consola de Logs (FFmpeg y Sistema)")
if st.button("🔄 Refrescar Logs"):
    st.rerun()

if os.path.exists(LOG_FILE):
    with open(LOG_FILE, "r", encoding="utf-8") as lf:
        log_lines = lf.readlines()
    # Mostrar los últimos 50 logs en orden inverso
    log_text = "".join(log_lines[-50:])
    st.text_area("Registro interno", value=log_text, height=250)
else:
    st.info("Aún no hay registros de log generados.")
