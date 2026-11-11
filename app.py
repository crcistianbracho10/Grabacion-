import os
import subprocess
import datetime
import threading
import time
import streamlit as st

PRIMARY_STREAM = "http://181.79.87.132:8000/play/a001/index.m3u8"
BACKUP_STREAM = "http://181.78.8.199:8000/play/a07l/index.m3u8"

RECORDINGS_DIR = "./temp_recordings"
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# Control de estado en Streamlit
if "is_recording" not in st.session_state:
    st.session_state.is_recording = False
if "current_process" not in st.session_state:
    st.session_state.current_process = None

def check_stream_working(url):
    try:
        cmd = ["ffmpeg", "-y", "-timeout", "5000000", "-i", url, "-t", "1", "-f", "null", "-"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)
        return res.returncode == 0
    except Exception:
        return False

def start_recording(duracion_minutos):
    if st.session_state.is_recording:
        st.warning("⚠️ Ya hay una grabación en curso.")
        return
    
    stream_to_use = PRIMARY_STREAM if check_stream_working(PRIMARY_STREAM) else BACKUP_STREAM
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
        st.session_state.current_process = subprocess.Popen(cmd)
        st.session_state.is_recording = True
        st.success(f"🔴 Grabación iniciada por {duracion_minutos} min.")
        
        # Hilo para detener automáticamente tras los minutos indicados
        duracion_segundos = duracion_minutos * 60
        def stop_after_timeout():
            time.sleep(duracion_segundos)
            stop_recording()

        threading.Thread(target=stop_after_timeout, daemon=True).start()
    except Exception as e:
        st.session_state.is_recording = False
        st.error(f"⚠️ Error al conectar: {str(e)}")

def stop_recording():
    if not st.session_state.is_recording or st.session_state.current_process is None:
        st.warning("⚠️ No hay ninguna grabación activa.")
        return
    try:
        st.session_state.current_process.terminate()
        st.session_state.current_process.wait(timeout=5)
    except Exception:
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
    cmd = ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "libmp3lame", "-q:a", "2", mp3_path]
    try:
        subprocess.run(cmd, check=True)
        return mp3_path
    except Exception:
        return None

def list_recordings():
    files = [f for f in os.listdir(RECORDINGS_DIR) if f.endswith('.mp4')]
    files.sort(reverse=True)
    return files

# Interfaz visual de Streamlit
st.set_page_config(page_title="Grabador Manual Streamlit", page_icon="🔴", layout="wide")

st.title("🔴 Grabador Manual de Streamings")
st.write("Panel de control rápido y estable para respaldar transmisiones cuando hay servicio eléctrico.")

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
        st.success("¡Espacio limpiado por completo!")
        st.rerun()
