"""Help / tutorial panel — explains how to set up cookies and use the app."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

HELP_HTML = """
<h2 style="color:#e94560;">Como usar o Super Video Downloader</h2>

<hr style="border:1px solid #2f3056;">

<h3 style="color:#e94560;">1. Requisitos (necessario para YouTube)</h3>

<p>O YouTube exige duas coisas para permitir downloads:</p>

<p><b style="color:#4caf50;">A) Node.js</b> — necessario para decifrar as URLs dos videos.</p>
<p>- Se voce usar o <b>start.bat</b>, ele instala automaticamente.<br>
- Senao, instale manualmente: abra um terminal e rode:<br>
<span style="color:#00ff41; font-family:monospace;">winget install OpenJS.NodeJS.LTS</span></p>

<p><b style="color:#4caf50;">B) Cookies do navegador</b> — o YouTube pede verificacao anti-bot.</p>

<p><b>Passo a passo para exportar cookies:</b></p>

<p><b>1.</b> Abra o <b>Edge</b> (ou Chrome) e instale a extensao
<span style="color:#4caf50;">"Get cookies.txt LOCALLY"</span>
na loja de extensoes do navegador.</p>

<p><b>2.</b> Acesse <span style="color:#4caf50;">youtube.com</span>
e faca login na sua conta Google.</p>

<p><b>3.</b> Clique no icone da extensao e exporte os cookies.
Vai baixar um arquivo <b>cookies.txt</b>.</p>

<p><b>4.</b> No app, na aba <b>Download</b>, clique em
<span style="color:#4caf50;">"Importar cookies.txt"</span>
e selecione o arquivo exportado.</p>

<p><b>5.</b> O status vai mudar para
<span style="color:#4caf50;">verde "Carregado"</span>.
Agora os downloads do YouTube vao funcionar!</p>

<p><b style="color:#e94560;">Dica:</b> Se voce salvar o arquivo como
<b>cookies.txt</b> na pasta do projeto, o app carrega automaticamente ao abrir.</p>

<p><b style="color:#e94560;">Apos formatar o PC:</b> Precisa reinstalar o Node.js
e exportar os cookies novamente.</p>

<hr style="border:1px solid #2f3056;">

<h3 style="color:#e94560;">2. Baixar Video ou Audio</h3>

<p>- Cole a URL do video na aba <b>Download</b>.<br>
- Escolha o modo: <b>So Baixar</b> ou <b>Baixar + Transcrever</b>.<br>
- Escolha o formato: <b>MP4</b> (video) ou <b>MP3</b> (so audio).<br>
- Clique em <b>INICIAR</b>.</p>

<hr style="border:1px solid #2f3056;">

<h3 style="color:#e94560;">3. Transcrever um video ja baixado</h3>

<p>- Clique no video no <b>Historico</b> (sidebar esquerda).<br>
- Clique no botao <b>Transcrever</b> abaixo da area de transcricao.<br>
- O idioma padrao e <b>Auto (detectar)</b> — funciona com qualquer lingua.</p>

<hr style="border:1px solid #2f3056;">

<h3 style="color:#e94560;">4. Player de video/audio</h3>

<p>- Clique em qualquer video no historico e a aba <b>Player</b> abre automaticamente.<br>
- Use os botoes <b>Play</b>, <b>Pause</b> e <b>Stop</b>.<br>
- Arraste a barra de progresso para navegar no video.<br>
- Para MP3, aparece um player de audio simplificado.</p>

<hr style="border:1px solid #2f3056;">

<h3 style="color:#e94560;">5. Gerenciar videos</h3>

<p>Clique com o <b>botao direito</b> em qualquer video no historico para:</p>

<p>- <b>Transcrever</b> — iniciar transcricao.<br>
- <b>Abrir pasta</b> — abre a pasta do arquivo no explorador.<br>
- <b>Renomear</b> — altera o titulo e renomeia o arquivo no disco.<br>
- <b>Alterar plataforma</b> — muda o badge (YT, TT, IG, FB, etc).<br>
- <b>Excluir</b> — apaga o video e o JSON do disco.</p>

<hr style="border:1px solid #2f3056;">

<h3 style="color:#e94560;">6. Atualizar yt-dlp</h3>

<p>Se um download falhar, tente clicar em <b>"Atualizar yt-dlp"</b> na aba Download.
Isso atualiza o motor de download para a versao mais recente.
O progresso aparece na aba <b>Console</b>.</p>

<hr style="border:1px solid #2f3056;">

<h3 style="color:#e94560;">7. Plataformas suportadas</h3>

<p>- <span style="color:#FF0000;font-weight:bold;">YouTube</span> (requer cookies)<br>
- <span style="color:#00f2ea;font-weight:bold;">TikTok</span><br>
- <span style="color:#E1306C;font-weight:bold;">Instagram</span><br>
- <span style="color:#1877F2;font-weight:bold;">Facebook</span><br>
- E qualquer outro site suportado pelo yt-dlp.</p>
"""


class HelpPanel(QWidget):
    """Scrollable help/tutorial panel."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QLabel(HELP_HTML)
        content.setWordWrap(True)
        content.setAlignment(Qt.AlignTop)
        content.setTextFormat(Qt.RichText)
        content.setStyleSheet(
            "QLabel { color: #f0f0f5; font-size: 13px; padding: 16px; "
            "background-color: #13131f; }"
        )
        content.setOpenExternalLinks(True)

        scroll.setWidget(content)
        layout.addWidget(scroll)
