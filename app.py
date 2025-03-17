import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext
from tkinter import filedialog
import subprocess
import whisper
import tempfile
import os
import sys
import torch

def baixar_audio_e_transcrever(url, lang_code):
    try:
        temp_dir = tempfile.gettempdir()
        temp_file_audio = os.path.join(temp_dir, "temp_audio.wav")

        if os.path.exists(temp_file_audio):
            os.remove(temp_file_audio)

        subprocess.run([
            sys.executable, "-m", "yt_dlp",
            "-f", "bestaudio[ext=m4a]/bestaudio",
            "-x", "--audio-format", "wav",
            "-o", f"{temp_dir}/temp_audio.%(ext)s",
            url
        ], check=True)

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = whisper.load_model("medium", device=device)
        result = model.transcribe(temp_file_audio, language=lang_code)
        texto = result["text"]

        if os.path.exists(temp_file_audio):
            os.remove(temp_file_audio)

        return texto.strip()
    except Exception as e:
        return f"Erro ao processar: {e}"

def transcrever_video_local(file_path, lang_code):
    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = whisper.load_model("medium", device=device)
        result = model.transcribe(file_path, language=lang_code)
        return result["text"].strip()
    except Exception as e:
        return f"Erro ao processar: {e}"

def gerar_transcricao():
    caminho = entrada_url.get().strip()
    idioma_selecionado = idioma_var.get()
    lang_code = "en" if idioma_selecionado == "English" else "pt"

    if caminho.startswith("http"):
        texto = baixar_audio_e_transcrever(caminho, lang_code)
    else:
        texto = transcrever_video_local(caminho, lang_code)

    caixa_texto.config(state="normal")
    caixa_texto.delete("1.0", tk.END)
    caixa_texto.insert(tk.END, texto)
    caixa_texto.config(state="disabled")

def copiar_texto():
    texto = caixa_texto.get("1.0", tk.END)
    janela.clipboard_clear()
    janela.clipboard_append(texto)

def buscar_arquivo():
    file_path = filedialog.askopenfilename(
        filetypes=[("Video/Audio Files", "*.mp4 *.mkv *.mov *.avi *.wav *.m4a"), ("All Files", "*.*")]
    )
    if file_path:
        entrada_url.delete(0, tk.END)
        entrada_url.insert(0, file_path)

janela = tk.Tk()
janela.title("Transcritor de Vídeo/Áudio")

frame_principal = ttk.Frame(janela, padding="10")
frame_principal.grid(row=0, column=0, sticky="NSEW")

label_url = ttk.Label(frame_principal, text="URL do YouTube ou Caminho do Arquivo:")
label_url.grid(row=0, column=0, padx=5, pady=5, sticky="W")
entrada_url = ttk.Entry(frame_principal, width=50)
entrada_url.grid(row=1, column=0, padx=5, pady=5, sticky="W")

botao_buscar = ttk.Button(frame_principal, text="Procurar Arquivo", command=buscar_arquivo)
botao_buscar.grid(row=1, column=1, padx=5, pady=5, sticky="W")

idioma_var = tk.StringVar()
idioma_var.set("English")
label_idioma = ttk.Label(frame_principal, text="Escolha o idioma do vídeo:")
label_idioma.grid(row=2, column=0, padx=5, pady=5, sticky="W")
dropdown_idioma = ttk.OptionMenu(frame_principal, idioma_var, "English", "English", "Portuguese (Brazil)")
dropdown_idioma.grid(row=3, column=0, padx=5, pady=5, sticky="W")

botao_gerar = ttk.Button(frame_principal, text="Generate", command=gerar_transcricao)
botao_gerar.grid(row=4, column=0, padx=5, pady=10, sticky="W")

caixa_texto = scrolledtext.ScrolledText(frame_principal, width=60, height=15, state="disabled")
caixa_texto.grid(row=5, column=0, padx=5, pady=5)

botao_copiar = ttk.Button(frame_principal, text="Copiar para Clipboard", command=copiar_texto)
botao_copiar.grid(row=6, column=0, padx=5, pady=5, sticky="W")

janela.mainloop()
