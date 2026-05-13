# Videos Pi — servico de download/transcricao no Raspberry Pi

Container Docker que roda no Pi e baixa videos (yt-dlp) + transcreve
(Deepgram). Arquivos saem em uma pasta sincronizada com o PC via
Syncthing, no **mesmo formato** que o app PySide6 espera — assim os
videos aparecem no historico do app PC automaticamente.

## Como funciona

```
Voce (celular/PC fora de casa)
        |  HTTPS via Tailscale
        v
Pi: container videos-pi
        - FastAPI + UI em /
        - REST API em /api/*
        - yt-dlp + ffmpeg + Node (yt-dlp-ejs)
        - Deepgram REST pra transcricao
        - Output em /output (volume montado)
                |
                v
Pi host: /media/devmon/sda1-ata-UP_GAMER_1TB_UP2/Syncthing/videos-app/
                |  Syncthing
                v
PC: D:\Syncthing\videos-app\  (ou onde voce decidir)
                |
                v
App PySide6 le essa pasta (precisa configurar — fase 3)
```

## Deploy no Pi (passo a passo)

### 1. Pre-requisitos no Pi

```bash
# Docker + Docker Compose (provavelmente ja instalados via CasaOS)
docker --version
docker compose version

# Pasta Syncthing que vai receber os downloads
sudo mkdir -p /media/devmon/sda1-ata-UP_GAMER_1TB_UP2/Syncthing/videos-app
sudo chmod -R 777 /media/devmon/sda1-ata-UP_GAMER_1TB_UP2/Syncthing/videos-app
```

> ⚠️ chmod 777 segue o padrao das outras pastas Syncthing do Marcelo
> (ver `raspberry data e apollo.txt`). Resolve UID/GID mismatch entre
> container e host.

### 2. Clonar o repo no Pi

```bash
cd ~
git clone https://github.com/marceloleitej/<repo-name>.git videos-pi
cd videos-pi/pi
```

Se ja existe, atualizar:

```bash
cd ~/videos-pi
git pull
```

### 3. Configurar `.env`

```bash
cp .env.example .env
nano .env
```

Preencher pelo menos `DEEPGRAM_API_KEY` (a mesma do `.env` do PC).
**Nao commitar** o `.env` — `.gitignore` ja cobre.

### 4. Subir o container

```bash
docker compose up -d --build
```

Primeiro build leva ~5-10min no Pi 4 (instala ffmpeg + nodejs +
pip deps). Builds seguintes usam cache e sao rapidos.

Verificar:

```bash
docker compose logs -f videos-pi
curl http://localhost:8080/api/health
```

Esperado: `{"ok": true, "output_dir": "/output", "deepgram_configured": true, ...}`.

### 5. Adicionar a pasta no Syncthing

Pelo Syncthing UI do Pi (http://marceloleitej-pi:8384):

1. **Add Folder**
2. Folder ID: `videos-app`
3. Folder Path: `/media/devmon/sda1-ata-UP_GAMER_1TB_UP2/Syncthing/videos-app`
4. Compartilhar com o device do PC
3. No Syncthing do PC, aceitar a pasta e salvar em `D:\Syncthing\videos-app`

### 6. Tailscale Serve (HTTPS via tailnet)

Pra acessar de fora pelo MagicDNS sem expor porta no roteador:

```bash
# IMPORTANTE: NAO usar :8443 — Pi-hole reivindica essa porta no host.
# Conflito leva o pi-hole a perder a rede no proximo restart do daemon.
sudo tailscale serve --bg --https=8444 http://localhost:8080
```

Acessar em: `https://marceloleitej-pi.tail92d61c.ts.net:8444`

(Tailscale cuida do cert TLS via Let's Encrypt na tailnet — funciona
em celular fora de casa desde que esteja conectado ao Tailscale.)

Pra desativar:

```bash
sudo tailscale serve reset
```

### 7. CasaOS (opcional — gerenciamento visual)

Adicionar o container no CasaOS:

1. Apps → Custom Install → From docker-compose
2. Cole o `docker-compose.yml`
3. CasaOS passa a mostrar status, logs, restart no painel

## Uso

A UI tem duas abas no topo: **Download** e **Biblioteca**.

### Aba Download
1. Abre `https://marceloleitej-pi.tail92d61c.ts.net:8444` no celular
2. Cola URL, escolhe mp4/mp3, marca transcrever (se quiser), escolhe idioma
3. Clica em "Adicionar a fila"
4. Acompanha progresso na lista — atualiza em tempo real
5. Quando termina, Syncthing replica pro PC em segundos
6. Abre o app PC: o video ja aparece no historico

### Aba Biblioteca
- Lista todo midia presente em `OUTPUT_DIR` (lendo os sidecars `*.json`).
- Filtro por plataforma (YouTube / TikTok / Instagram / Facebook / Outro). Opcoes sao geradas dinamicamente conforme o que existe na pasta.
- Click no item -> player HTML5 inline (`<video>` pra mp4, `<audio>` pra mp3). Streaming via rota `/media/<arquivo>` montada com `StaticFiles` (suporta HTTP Range nativo, entao seek funciona).

## API REST

| Endpoint | Metodo | Body | Retorno |
|---|---|---|---|
| `/api/health` | GET | — | status do servico |
| `/api/download` | POST | `{url, format, transcribe, language}` | job criado |
| `/api/jobs` | GET | — | lista de jobs |
| `/api/jobs/{id}` | GET | — | detalhes |
| `/api/jobs/{id}/cancel` | POST | — | cancela job ativo |
| `/api/jobs/{id}` | DELETE | — | remove job terminal |
| `/api/library` | GET | — | lista videos em `OUTPUT_DIR` (title, platform, format, duration, `media_url`) |
| `/media/<arquivo>` | GET | — | streaming do arquivo (StaticFiles, com Range) |

Exemplo curl:

```bash
curl -X POST http://localhost:8080/api/download \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://youtube.com/watch?v=...", "format": "mp4", "transcribe": true, "language": "pt-BR"}'
```

## Variaveis de ambiente

| Var | Default | Descricao |
|---|---|---|
| `DEEPGRAM_API_KEY` | — | Chave da API Deepgram (obrigatoria pra transcricao) |
| `DEFAULT_LANGUAGE` | `pt-BR` | Idioma default selecionado no UI |
| `MAX_CONCURRENT_JOBS` | `2` | Quantos downloads rodam em paralelo |
| `JOB_HISTORY_LIMIT` | `50` | Quantos jobs terminais ficam visiveis na lista |
| `OUTPUT_DIR` (host) | `/media/devmon/.../videos-app` | Path no host mapeado pra `/output` |
| `HOST_PORT` | `8080` | Porta do host onde o servico ouve |

## Troubleshooting

### "Cannot connect to the Docker daemon"

```bash
sudo systemctl start docker
sudo usermod -aG docker $USER  # depois de logout/login funciona sem sudo
```

### Build trava em `pip install`

Pi 4 com 8GB tem RAM suficiente, mas verifique swap:

```bash
free -h
# Se Swap: 0B, ative:
sudo dphys-swapfile setup
sudo systemctl restart dphys-swapfile
```

### Video baixa mas nao aparece no PC

1. Confere que a pasta `/media/.../videos-app/` no Pi tem o `.mp4` + `.mp4.json`
2. Confere que o Syncthing do Pi esta sincronizando essa pasta
3. Confere que o PC recebeu (olha em `D:\Syncthing\videos-app\`)
4. Confere que o app PC esta apontando pra essa pasta (fase 3 — TODO)

### Erro de permissao escrevendo em `/output`

```bash
sudo chmod -R 777 /media/devmon/sda1-ata-UP_GAMER_1TB_UP2/Syncthing/videos-app
docker compose restart videos-pi
```

### yt-dlp falha (assinaturas YouTube)

Atualizar a imagem:

```bash
docker compose pull   # se voce versionar a imagem em registry
# ou
docker compose build --no-cache videos-pi
docker compose up -d videos-pi
```

## Logs

```bash
docker compose logs -f videos-pi              # streaming
docker compose logs --tail 100 videos-pi      # ultimas 100 linhas
```

## Parar / remover

```bash
docker compose down              # para o container
docker compose down --rmi local  # para + remove imagem
```

Os arquivos baixados ficam no host — nao sao removidos.
