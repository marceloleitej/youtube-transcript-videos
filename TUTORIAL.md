# Super Video Downloader — Tutorial de instalação

App PySide6 para baixar vídeos (YouTube, TikTok, Instagram, Facebook), transcrever com Deepgram e tocar áudio com player nativo (ffmpeg + PortAudio).

Este tutorial cobre instalação e uso em um **PC novo, do zero**, no Windows 10/11.

---

## 1. Requisitos

### 1.1 Obrigatórios

| Componente | Versão mínima | Por quê |
|---|---|---|
| **Windows 10/11** | x64 | Plataforma alvo (`start.bat`, `pythonw.exe`, `winget`) |
| **Python** | 3.10+ | Runtime do app |
| **Node.js** | LTS (20+) | Necessário para o `yt-dlp-ejs` resolver players do YouTube |
| **ffmpeg + ffprobe** | qualquer recente | Decodificação de áudio (player) e detecção de stream |
| **Git** | qualquer | Para clonar o repo |

### 1.2 Opcionais

- **Conta Deepgram + API key** — só necessário se você quer **transcrever** áudio. Crie em https://deepgram.com (tem tier gratuito).
- **GPU NVIDIA com CUDA** — não é mais necessário (a transcrição agora é via API Deepgram, não Whisper local).

---

## 2. Instalar dependências do sistema

### 2.1 Python 3.10+

Baixe em https://www.python.org/downloads/windows/. **Marque "Add Python to PATH"** durante a instalação.

Verifique:

```powershell
python --version
```

### 2.2 Git

Baixe em https://git-scm.com/download/win e instale com as opções padrão.

### 2.3 Node.js (LTS)

Opção A — via winget (já incluso no `start.bat`):

```powershell
winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
```

Opção B — instalador oficial: https://nodejs.org/

Verifique:

```powershell
node --version
```

### 2.4 ffmpeg (com ffprobe)

O `ffprobe.exe` precisa estar acessível pelo `PATH` ou em `C:\Program Files\ffmpeg\bin\` ou `C:\ffmpeg\bin\` (o app procura nesses locais).

Opção A — via winget:

```powershell
winget install Gyan.FFmpeg
```

Opção B — manual:

1. Baixe um build em https://www.gyan.dev/ffmpeg/builds/ (release essentials).
2. Extraia para `C:\ffmpeg\` (de modo que `C:\ffmpeg\bin\ffmpeg.exe` exista).
3. Adicione `C:\ffmpeg\bin` ao `PATH` do sistema.

Verifique:

```powershell
ffmpeg -version
ffprobe -version
```

---

## 3. Clonar o repositório

```powershell
cd D:\
git clone https://github.com/marceloleitej/youtube-transcript-videos.git
cd youtube-transcript-videos
```

---

## 4. Configurar o ambiente Python

O `start.bat` faz isso automaticamente, mas se quiser fazer manual:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Pacotes instalados (ver `requirements.txt`):

- `PySide6` — UI Qt6
- `yt-dlp` + `yt-dlp-ejs` — download
- `httpx` — cliente HTTP (Deepgram)
- `python-dotenv` — carregar `.env`
- `sounddevice` — wrapper PortAudio para player nativo
- `numpy` — buffers de áudio

---

## 5. Configurar a API key do Deepgram (opcional)

Sem isso, o download/player funcionam — só a **transcrição** fica indisponível.

1. Crie conta em https://deepgram.com e gere uma API key.
2. Na raiz do projeto, crie um arquivo `.env`:

```
DEEPGRAM_API_KEY=sua_chave_aqui
```

O `.env` está no `.gitignore` — ele nunca vai para o GitHub.

---

## 6. Rodar o app

### 6.1 Modo recomendado (1 clique)

Execute o `start.bat`:

```powershell
.\start.bat
```

Esse script:

1. Cria `.venv` se não existir
2. Instala dependências
3. Verifica Node.js (instala via winget se faltar)
4. Sobe o app sem janela de console (`pythonw.exe`)

### 6.2 Modo manual (com console visível para debug)

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

---

## 7. Estrutura do projeto

```
.
├── app.py                  # Entry point (cria QApplication, instala redirect de console)
├── start.bat               # Script de boot 1-clique
├── requirements.txt
├── icon.ico / icon.png     # Ícone do app (Alt+Tab, taskbar)
├── _check_env.py           # Diagnóstico rápido de ambiente
├── core/
│   ├── store.py            # Persistência JSON sidecar de cada vídeo
│   ├── downloader.py       # Wrapper do yt-dlp (YouTube/TikTok/Instagram/Facebook)
│   ├── transcriber.py      # Cliente Deepgram (REST batch)
│   ├── audio_engine.py     # Player nativo: ffmpeg → ring buffer → PortAudio
│   ├── thumbnails.py       # Geração de thumbnails
│   ├── ai_summary.py       # Resumo com IA
│   └── platform_detect.py  # Detecta plataforma a partir da URL
├── ui/
│   ├── main_window.py      # Janela principal + workers QThread
│   ├── download_panel.py   # Painel de download (URL, opções, progresso)
│   ├── history_panel.py    # Histórico de mídias baixadas (sidebar)
│   ├── audio_player.py     # Controles do player de áudio
│   ├── video_player.py     # Player de vídeo
│   ├── transcript_viewer.py
│   ├── local_transcribe_panel.py
│   ├── ai_summary_dialog.py
│   ├── help_panel.py
│   ├── console_panel.py    # Console interno (captura stdout/stderr)
│   ├── design_tokens.py    # Cores/temas
│   ├── icons.py / spinner.py
└── output/                 # (gerado) mídias baixadas + JSON sidecars
```

Cada vídeo baixado vira um par `arquivo.mp4` + `arquivo.json` em `output/`. O JSON guarda metadata (URL original, plataforma, data, transcrição, pasta virtual, etc.).

---

## 8. Resolução de problemas

### "Node.js não encontrado"

O `start.bat` deveria instalar via winget. Se falhar, instale manual em https://nodejs.org/ e reinicie o terminal.

### "ffprobe não encontrado" / áudio não toca

Verifique:

```powershell
where ffmpeg
where ffprobe
```

Se não retornar nada, o `PATH` não está pegando. Adicione `C:\ffmpeg\bin` ao `Path` em **Variáveis de Ambiente** ou copie os exes para um diretório já no PATH.

### YouTube falha com "Sign in to confirm you're not a bot"

YouTube bloqueia IPs frios. Soluções:

1. **Cookies do navegador**: configure um arquivo de cookies (Netscape format) e aponte no app. Há extensões de navegador que exportam cookies.
2. **VPN / IP residencial** se estiver atrás de IP de datacenter.

### Transcrição falha

- Verifique que `.env` tem `DEEPGRAM_API_KEY=...` válido.
- Verifique saldo/limites da conta Deepgram.
- Se o vídeo não tem áudio, o app mostra `NoAudioTrackError` — esperado.

### App "trava" / fecha após muito tempo aberto

Já corrigido: o console interno tinha crescimento ilimitado. A versão atual usa `setMaximumBlockCount(5000)` no QTextEdit + `deque(maxlen=10000)` no buffer redirector. Se ainda observar, reporte.

### Diagnóstico rápido

```powershell
.\.venv\Scripts\python.exe _check_env.py
```

Imprime `python.exe`, `prefix` e versão do `PySide6`.

---

## 9. Atualizar (pull de novas versões)

```powershell
cd D:\youtube-transcript-videos
git pull
.\.venv\Scripts\pip.exe install -r requirements.txt --upgrade
```

---

## 10. Desinstalar

Apague a pasta inteira do projeto. O app não escreve fora dela (exceto `.env` que você criou e a própria venv que mora dentro).
