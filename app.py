import os
import subprocess
import datetime
import threading
import time
import schedule
import streamlit as st
from huggingface_hub import HfApi

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
if "scheduler_started" not in st.session_state:
    st.session_state.scheduler_started = False
if "last_recorded_file" not in st.session_state:
    st.session_state.last_recorded_file = None

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
        return res.returncode == 0
    except Exception as e:
        write_log(f"Excepción al comprobar stream {url}: {str(e)}")
        return False

def subir_a_hf_dataset(file_path):
    try:
        if "HF_TOKEN" not in st.secrets:
            write_log("⚠️ No se encontró HF_TOKEN en st.secrets. No se pudo subir a Hugging Face.")
            return
        
        token = st.secrets["HF_TOKEN"]
        api = HfApi(token=token)
        
        write_log(f"Subiendo {os.path.basename(file_path)} al dataset cristianbracho904/Grabacionjd...")
        api.upload_file(
            path_or_fileobj=file_path,
            path_in_repo=os.path.basename(file_path),
            repo_id="cristianbracho904/Grabacionjd",
            repo_type="dataset"
        )
        write_log("✅ ¡Archivo respaldado exitosamente en Hugging Face Dataset!")
    except Exception as e:
        write_log(f"❌ Error subiendo a Hugging Face Dataset: {str(e)}")

def ejecutar_grabacion(duracion_minutos, origen="Manual"):
    if st.session_state.is_recording:
        write_log(f"[{origen}] Intento de grabar pero ya hay una grabación en curso.")
        return
    
    write_log(f"[{origen}] Intentando iniciar nueva grabación por {duracion_minutos} min...")
    stream_to_use = PRIMARY_STREAM if check_stream_working(PRIMARY_STREAM) else BACKUP_STREAM
    write_log(f"Stream seleccionado: {stream_to_use}")
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filepath = os.path.join(RECORDINGS_DIR, f"grabacion_{timestamp}.mp4")
    st.session_state.last_recorded_file = output_filepath
    
    cmd = [
        "ffmpeg", "-y",
        "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
        "-i", stream_to_use,
        "-c:v", "copy", "-c:a", "aac",
        "-bsf:a", "aac_adtstoasc",
        output_filepath
    ]
    
    try:
        log_output = open(LOG_FILE, "a", encoding="utf-8")
        st.session_state.current_process = subprocess.Popen(cmd, stdout=log_output, stderr=log_output)
        st.session_state.is_recording = True
        write_log(f"🔴 Grabación iniciada. Guardando en: {output_filepath}")
        
        duracion_segundos = duracion_minutos * 60
        def stop_after_timeout():
            time.sleep(duracion_segundos)
            stop_recording(origen="Automático/Timeout")

        threading.Thread(target=stop_after_timeout, daemon=True).start()
    except Exception as e:
        st.session_state.is_recording = False
        write_log(f"⚠️ Error crítico al iniciar FFmpeg: {str(e)}")

def stop_recording(origen="Manual"):
    if not st.session_state.is_recording or st.session_state.current_process is None:
        write_log(f"[{origen}] Intento de detener grabación pero no hay ninguna activa.")
        return
    try:
        write_log(f"[{origen}] Deteniendo proceso de grabación...")
        st.session_state.current_process.terminate()
        st.session_state.current_process.wait(timeout=5)
        write_log("Proceso detenido correctamente.")
    except Exception as e:
        write_log(f"Fuerza bruta al matar proceso FFmpeg: {str(e)}")
        st.session_state.current_process.kill()
    finally:
        st.session_state.current_process = None
        st.session_state.is_recording = False
        write_log("⏹️ Grabación detenida y guardada localmente.")
        
        # Subir automáticamente a Hugging Face Dataset appena termine
        if st.session_state.last_recorded_file and os.path.exists(st.session_state.last_recorded_file):
            subir_a_hf_dataset(st.session_state.last_recorded_file)

# Configurar el planificador automático (Lunes a Viernes)
def run_scheduler():
    schedule.every().monday.through(schedule.friday).at("06:38").do(ejecutar_grabacion, duracion_minutos=40, origen="Horario 11:38AM")
    schedule.every().monday.through(schedule.friday).at("18:10").do(ejecutar_grabacion, duracion_minutos=40, origen="Horario 6:10PM")
    
    while True:
        schedule.run_pending()
        time.sleep(30)

if not st.session_state.scheduler_started:
    threading.Thread(target=run_scheduler, daemon=True).start()
    st.session_state.scheduler_started = True
    write_log("Planificador automático de horarios iniciado en segundo plano.")

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
        return mp3_path
    except Exception as e:
        write_log(f"Error convirtiendo a MP3: {str(e)}")
        return None

def list_recordings():
    files = [f for f in os.listdir(RECORDINGS_DIR) if f.endswith('.mp4')]
    files.sort(reverse=True)
    return files

# Interfaz visual de Streamlit
st.set_page_config(page_title="Grabador Automatizado con HF Backup", page_icon="🔴", layout="wide")

st.title("🔴 Grabador Automático con Respaldo en Hugging Face")
st.write("📅 **Horarios activos (Lunes a Viernes):** **11:38 AM** y respaldo a las **6:10 PM** (60 min). Sube automáticamente a `cristianbracho904/Grabacionjd`.")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Control Manual y Pruebas")
    duracion = st.slider("Duración de prueba (Minutos):", min_value=1, max_value=180, value=3, step=1)
    
    if st.button("⚡ Iniciar Grabación de Prueba", type="primary", use_container_width=True):
        ejecutar_grabacion(duracion, origen="Prueba Manual")
        st.rerun()
        
    if st.button("🛑 Detener Grabación Activa", use_container_width=True):
        stop_recording(origen="Manual Web")
        st.rerun()

    estado_actual = "🔴 Grabando en segundo plano y respaldando..." if st.session_state.is_recording else "🟢 Sistema en espera (Horarios activos)."
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
        write_log("Servidor limpiado por completo.")
        st.success("¡Espacio limpiado!")
        st.rerun()

# Visor de Logs
st.subheader("📋 Consola de Logs (Historial de Grabación y Subida)")
if st.button("🔄 Refrescar Logs"):
    st.rerun()

if os.path.exists(LOG_FILE):
    with open(LOG_FILE, "r", encoding="utf-8") as lf:
        log_lines = lf.readlines()
    log_text = "".join(log_lines[-50:])
    st.text_area("Registro interno", value=log_text, height=250)
else:
    st.info("Aún no hay registros.")
