"""High-quality music playback engine.

Why not QMediaPlayer: on Windows with PySide6, QMediaPlayer's audio path
runs decoded PCM through a buffer small enough that any Python GIL stall
(garbage collection, UI redraw, history panel rebuild, main-thread spike
from unrelated work) can starve the output and produce micro-glitches —
especially under CPU load.

This engine decouples decoding from the Python thread entirely:

  [file] -> ffmpeg subprocess -> stdout pipe -> python consumer thread
         -> ring buffer -> sounddevice callback (native audio thread) -> out

- ffmpeg is a separate OS process, so MP3 decoding is GIL-immune.
- sounddevice (PortAudio) runs its callback in a native thread. Our Python
  callback only copies bytes out of the ring buffer — cheap, fast.
- The ring buffer is sized for ~1s of audio, absorbing any multi-hundred-ms
  Python stall without an underrun.
- ffmpeg's `atempo` audio filter gives pitch-preserving speed control.

Public API mirrors what ui/audio_player.py used from QMediaPlayer/QAudioOutput
so the rest of the UI keeps working with minimal changes.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading

import numpy as np
import sounddevice as sd
from PySide6.QtCore import Qt, QObject, QTimer, Signal


# --- Playback format (Windows default mixer is 48k stereo 16-bit) ---
SAMPLE_RATE = 48000
CHANNELS = 2
SAMPLE_WIDTH = 2  # int16
BYTES_PER_FRAME = SAMPLE_WIDTH * CHANNELS

# Buffer targets (in frames)
RING_BUFFER_TARGET_FRAMES = SAMPLE_RATE        # ~1.0s of audio
RING_BUFFER_MAX_FRAMES = SAMPLE_RATE * 2       # ~2.0s (backpressure threshold)
CALLBACK_BLOCK_FRAMES = 2048                   # ~43ms per audio callback


# --- State / Status enums (keep name-compatible with QMediaPlayer-ish logic) ---
class State:
    StoppedState = "stopped"
    PlayingState = "playing"
    PausedState = "paused"


class MediaStatus:
    NoMedia = "no_media"
    LoadingMedia = "loading"
    LoadedMedia = "loaded"
    BufferingMedia = "buffering"
    BufferedMedia = "buffered"
    EndOfMedia = "end_of_media"
    InvalidMedia = "invalid"


def _find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if exe:
        return exe
    for cand in (
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
    ):
        if os.path.isfile(cand):
            return cand
    return "ffmpeg"  # will fail at Popen if truly missing


def _find_ffprobe() -> str:
    exe = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if exe:
        return exe
    for cand in (
        r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
        r"C:\ffmpeg\bin\ffprobe.exe",
    ):
        if os.path.isfile(cand):
            return cand
    return "ffprobe"


def _atempo_chain(rate: float) -> str:
    """Build an `atempo` filter chain for any rate in [0.25, 4.0].

    Single atempo clamps 0.5..100. Outside 0.5..2 we chain instances, each
    staying within range, so total product == requested rate.
    """
    if abs(rate - 1.0) < 1e-3:
        return ""
    parts = []
    r = float(rate)
    while r < 0.5:
        parts.append("atempo=0.5")
        r /= 0.5
    while r > 2.0:
        parts.append("atempo=2.0")
        r /= 2.0
    parts.append(f"atempo={r:.6f}")
    return ",".join(parts)


class AudioEngine(QObject):
    """Drop-in style replacement for QMediaPlayer + QAudioOutput (audio only)."""

    # Signals mirror the subset of QMediaPlayer signals we actually use.
    positionChanged = Signal(int)         # ms
    durationChanged = Signal(int)         # ms
    playbackStateChanged = Signal()       # fetch via state()
    mediaStatusChanged = Signal(object)   # MediaStatus.*

    # Internal: probe thread -> UI thread bounce (queued via Qt::QueuedConnection)
    _probeFinished = Signal(str, int)     # (source_path, duration_ms)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._source: str = ""
        self._duration_ms: int = 0
        self._rate: float = 1.0
        self._volume: float = 0.8
        self._muted: bool = False

        self._state: str = State.StoppedState
        self._status: str = MediaStatus.NoMedia

        # Ring buffer of raw int16 interleaved stereo bytes
        self._buf = bytearray()
        self._buf_lock = threading.Lock()
        self._buf_cv = threading.Condition(self._buf_lock)

        # Playback position, counted by the audio callback in frames.
        # `_base_ms` is the ms offset at which the current ffmpeg decode
        # started (non-zero after seek or speed change).
        self._played_frames: int = 0
        self._base_ms: int = 0
        self._eof_from_decoder = False
        self._end_emitted = False

        self._proc: subprocess.Popen | None = None
        self._decode_thread: threading.Thread | None = None
        self._stop_flag = threading.Event()

        self._stream: sd.RawOutputStream | None = None

        # Position emission at 4 Hz (slider + time label updates in UI)
        self._pos_timer = QTimer(self)
        self._pos_timer.setInterval(250)
        self._pos_timer.timeout.connect(self._emit_position_tick)

        self._ffmpeg = _find_ffmpeg()
        self._ffprobe = _find_ffprobe()

        # Bounce probe results to the UI thread - QueuedConnection ensures
        # the slot runs on this engine's owning (Qt) thread regardless of
        # which thread emits the signal.
        self._probeFinished.connect(
            self._on_duration_probed, Qt.QueuedConnection
        )

    # ------------- Public API (QMediaPlayer-ish) -------------

    def source(self) -> str:
        return self._source

    def sourceIsEmpty(self) -> bool:
        return not self._source

    def duration(self) -> int:
        return self._duration_ms

    def position(self) -> int:
        return int(self._base_ms + (self._played_frames / SAMPLE_RATE) * 1000)

    def playbackState(self) -> str:
        return self._state

    def setSource(self, path: str) -> None:
        self._teardown_pipeline()
        self._source = path or ""
        self._played_frames = 0
        self._base_ms = 0
        self._duration_ms = 0
        self._end_emitted = False

        if not self._source:
            self._set_status(MediaStatus.NoMedia)
            return

        self._set_status(MediaStatus.LoadingMedia)

        # Run ffprobe off the UI thread. A bad/missing/network file can take
        # seconds to time out, and doing that synchronously in setSource()
        # freezes the whole window. We snapshot the source path so a quick
        # subsequent setSource() invalidates this probe's result.
        target_source = self._source
        threading.Thread(
            target=self._probe_worker,
            args=(target_source,),
            name="AudioProbe",
            daemon=True,
        ).start()

    def _probe_worker(self, target_source: str) -> None:
        ms = self._probe_duration_ms(target_source)
        # Bounce result back to the Qt thread via signal+QueuedConnection.
        # (QTimer.singleShot from a non-Qt thread silently drops because the
        # calling thread has no event loop.)
        self._probeFinished.emit(target_source, ms)

    def _on_duration_probed(self, source_path: str, duration_ms: int) -> None:
        # Drop result if the user moved on to another track meanwhile.
        if source_path != self._source:
            return
        self._duration_ms = duration_ms
        self.durationChanged.emit(duration_ms)
        if duration_ms > 0:
            self._set_status(MediaStatus.LoadedMedia)
        else:
            self._set_status(MediaStatus.InvalidMedia)

    def play(self) -> None:
        if not self._source:
            return
        if self._state == State.PlayingState:
            return
        if self._state == State.PausedState and self._stream is not None:
            try:
                self._stream.start()
                self._set_state(State.PlayingState)
                self._pos_timer.start()
                return
            except Exception:
                self._teardown_pipeline()
        # Fresh pipeline from current position
        self._start_pipeline(start_ms=self.position())

    def pause(self) -> None:
        if self._state != State.PlayingState:
            return
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
        self._set_state(State.PausedState)
        self._pos_timer.stop()
        self.positionChanged.emit(self.position())

    def stop(self) -> None:
        self._teardown_pipeline()
        self._played_frames = 0
        self._base_ms = 0
        self._set_state(State.StoppedState)
        self._pos_timer.stop()
        self.positionChanged.emit(0)

    def setPosition(self, ms: int) -> None:
        ms = max(0, int(ms))
        if self._duration_ms > 0:
            ms = min(ms, self._duration_ms)
        was_playing = self._state == State.PlayingState
        self._teardown_pipeline()
        self._played_frames = 0
        self._base_ms = ms
        self.positionChanged.emit(ms)
        if was_playing:
            self._start_pipeline(start_ms=ms)
        else:
            self._set_state(State.PausedState)

    def setPlaybackRate(self, rate: float) -> None:
        rate = float(rate)
        if abs(rate - self._rate) < 1e-4:
            return
        cur_ms = self.position()
        was_playing = self._state == State.PlayingState
        self._rate = rate
        self._teardown_pipeline()
        self._played_frames = 0
        self._base_ms = cur_ms
        if was_playing:
            self._start_pipeline(start_ms=cur_ms)

    # ---- Volume / mute (replaces QAudioOutput) ----

    def setVolume(self, v: float) -> None:
        self._volume = max(0.0, min(1.0, float(v)))

    def volume(self) -> float:
        return self._volume

    def setMuted(self, muted: bool) -> None:
        self._muted = bool(muted)

    def isMuted(self) -> bool:
        return self._muted

    # ---- Cleanup for app shutdown ----

    def shutdown(self) -> None:
        try:
            self._pos_timer.stop()
        except Exception:
            pass
        self._teardown_pipeline()

    # ------------- Internals -------------

    def _set_state(self, s: str) -> None:
        if s == self._state:
            return
        self._state = s
        self.playbackStateChanged.emit()

    def _set_status(self, s: str) -> None:
        if s == self._status:
            return
        self._status = s
        self.mediaStatusChanged.emit(s)

    def _probe_duration_ms(self, path: str) -> int:
        try:
            proc = subprocess.run(
                [self._ffprobe, "-v", "error",
                 "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1",
                 path],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            return int(float((proc.stdout or "0").strip()) * 1000)
        except Exception:
            return 0

    def _build_ffmpeg_cmd(self, start_ms: int) -> list[str]:
        cmd = [self._ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin"]
        start_s = max(0, start_ms) / 1000.0
        if start_s > 0:
            # -ss before -i is fast seek (close enough for music)
            cmd += ["-ss", f"{start_s:.3f}"]
        cmd += ["-i", self._source]
        atempo = _atempo_chain(self._rate)
        if atempo:
            cmd += ["-filter:a", atempo]
        cmd += [
            "-f", "s16le",
            "-ac", str(CHANNELS),
            "-ar", str(SAMPLE_RATE),
            "-",
        ]
        return cmd

    def _start_pipeline(self, start_ms: int) -> None:
        self._stop_flag.clear()
        self._end_emitted = False
        self._eof_from_decoder = False
        with self._buf_lock:
            self._buf.clear()

        try:
            self._proc = subprocess.Popen(
                self._build_ffmpeg_cmd(start_ms),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                bufsize=0,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except FileNotFoundError:
            self._set_status(MediaStatus.InvalidMedia)
            return

        self._decode_thread = threading.Thread(
            target=self._decode_loop, name="AudioDecode", daemon=True
        )
        self._decode_thread.start()

        try:
            self._stream = sd.RawOutputStream(
                samplerate=SAMPLE_RATE,
                blocksize=CALLBACK_BLOCK_FRAMES,
                channels=CHANNELS,
                dtype="int16",
                callback=self._audio_callback,
                latency="high",  # let PortAudio pick a comfortable latency
            )
            self._stream.start()
        except Exception:
            self._teardown_pipeline()
            self._set_status(MediaStatus.InvalidMedia)
            return

        self._set_state(State.PlayingState)
        self._set_status(MediaStatus.BufferedMedia)
        self._pos_timer.start()

    def _decode_loop(self) -> None:
        """Pump ffmpeg stdout into the ring buffer with backpressure."""
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            while not self._stop_flag.is_set():
                # Backpressure: wait if buffer is already large.
                with self._buf_cv:
                    while (
                        len(self._buf) >= RING_BUFFER_MAX_FRAMES * BYTES_PER_FRAME
                        and not self._stop_flag.is_set()
                    ):
                        self._buf_cv.wait(timeout=0.1)
                    if self._stop_flag.is_set():
                        return

                chunk = proc.stdout.read(8192)
                if not chunk:
                    with self._buf_cv:
                        self._eof_from_decoder = True
                        self._buf_cv.notify_all()
                    return
                with self._buf_cv:
                    self._buf.extend(chunk)
                    self._buf_cv.notify_all()
        except Exception:
            with self._buf_cv:
                self._eof_from_decoder = True
                self._buf_cv.notify_all()

    def _audio_callback(self, outdata, frames, time_info, status) -> None:
        """Called on PortAudio's native thread. Keep this lean."""
        needed = frames * BYTES_PER_FRAME
        raw: bytes
        eof_now = False
        with self._buf_lock:
            if len(self._buf) >= needed:
                raw = bytes(self._buf[:needed])
                del self._buf[:needed]
                self._buf_cv.notify_all()
                self._played_frames += frames
            else:
                # Underrun or genuine EOF
                available = bytes(self._buf)
                del self._buf[:]
                self._buf_cv.notify_all()
                if self._eof_from_decoder and not available:
                    # True end of stream
                    outdata[: len(outdata)] = b"\x00" * len(outdata)
                    eof_now = True
                    raw = b""
                else:
                    # Pad with silence (underrun)
                    raw = available + b"\x00" * (needed - len(available))
                    self._played_frames += frames

        if not eof_now:
            # Apply mute / volume without allocating where possible
            if self._muted:
                outdata[: len(raw)] = b"\x00" * len(raw)
            elif self._volume >= 0.999:
                outdata[: len(raw)] = raw
            else:
                # Scale int16 by volume
                gain = int(self._volume * 32768) / 32768.0
                arr = np.frombuffer(raw, dtype=np.int16)
                scaled = (arr.astype(np.int32) * int(gain * 4096) // 4096).astype(np.int16)
                outdata[: len(raw)] = scaled.tobytes()

        if eof_now:
            # Tell PortAudio to stop the stream; UI side picks up via timer.
            raise sd.CallbackStop

    def _emit_position_tick(self) -> None:
        pos = self.position()
        if self._duration_ms > 0 and pos > self._duration_ms:
            pos = self._duration_ms
        self.positionChanged.emit(pos)

        # End-of-media detection: decoder is done AND buffer fully drained.
        if (
            not self._end_emitted
            and self._eof_from_decoder
            and (self._stream is None or not self._stream.active)
        ):
            self._end_emitted = True
            self._pos_timer.stop()
            self._set_state(State.StoppedState)
            self._set_status(MediaStatus.EndOfMedia)

    def _teardown_pipeline(self) -> None:
        # 1) Signal everyone we're tearing down and unblock any cv waiters.
        self._stop_flag.set()
        with self._buf_cv:
            self._buf_cv.notify_all()

        # 2) Stop the audio stream first - it doesn't need ffmpeg to die.
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        # 3) Kill ffmpeg. Order matters: closing stdout first makes any
        #    blocking proc.stdout.read() in the decode thread return EOF
        #    immediately, so the thread can exit while we still terminate
        #    the OS process. We then ALWAYS verify via poll() that the
        #    process is dead before dropping our reference - never trust
        #    that terminate()+wait() succeeded based on no-exception alone.
        proc = self._proc
        if proc is not None:
            try:
                if proc.stdout is not None:
                    proc.stdout.close()
            except Exception:
                pass
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=1.0)
            except Exception:
                pass
            # Guarantee no zombie: if it's still alive, force kill and wait.
            try:
                if proc.poll() is None:
                    proc.kill()
                    try:
                        proc.wait(timeout=0.5)
                    except Exception:
                        pass
            except Exception:
                pass
            # Drain stderr/stdout file objects so subprocess doesn't hold
            # OS handles after we drop the reference.
            for stream_attr in ("stdout", "stderr", "stdin"):
                s = getattr(proc, stream_attr, None)
                if s is not None:
                    try:
                        s.close()
                    except Exception:
                        pass
            self._proc = None

        # 4) Join the decode thread. With stdout already closed and the
        #    stop flag set, it should exit quickly. If it doesn't (rare:
        #    Windows pipe quirk), don't block the UI - the thread is a
        #    daemon and the next start_pipeline will spawn a fresh one.
        if self._decode_thread is not None:
            try:
                self._decode_thread.join(timeout=1.0)
            except Exception:
                pass
            self._decode_thread = None

        with self._buf_lock:
            self._buf.clear()
