from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSlider, QPushButton, QLabel

from ..core.progress import fmt_duration


class PlayerBox(QWidget):
    ended = Signal()

    def __init__(self):
        super().__init__()
        # في الوضع Headless (الاختبار الآلي بلا شاشة/صوت) لا نُنشئ مشغّل Qt Multimedia
        self.headless = QGuiApplication.platformName() in ("offscreen", "minimal")
        self.range = None
        if self.headless:
            self.player = None
            lay = QVBoxLayout(self)
            lay.addWidget(QLabel("(player disabled in headless mode)"))
            return
        from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
        from PySide6.QtMultimediaWidgets import QVideoWidget
        self._QMP = QMediaPlayer
        self.video = QVideoWidget()
        self.video.setMinimumSize(320, 200)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.range = None
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedWidth(44)
        self.play_btn.clicked.connect(self.toggle)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.sliderMoved.connect(self.player.setPosition)
        self.time = QLabel("00:00 / 00:00")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.video, 1)
        row = QHBoxLayout()
        for w in (self.play_btn, self.slider, self.time):
            row.addWidget(w)
        lay.addLayout(row)
        self.player.positionChanged.connect(self._pos)
        self.player.durationChanged.connect(lambda d: self.slider.setRange(0, d))
        self.player.mediaStatusChanged.connect(self._status)
        self.player.playbackStateChanged.connect(
            lambda s: self.play_btn.setText("⏸" if s == QMediaPlayer.PlayingState else "▶"))

    def _pos(self, pos):
        if not self.slider.isSliderDown():
            self.slider.setValue(pos)
        self.time.setText(f"{fmt_duration(pos / 1000)} / {fmt_duration(self.player.duration() / 1000)}")
        if self.range and pos / 1000 >= self.range[1]:
            self.player.pause()
            self.range = None

    def _status(self, st):
        if st == self._QMP.EndOfMedia:
            self.ended.emit()

    def load(self, path, autoplay=False):
        if self.player is None:
            return
        self.range = None
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        if autoplay:
            self.player.play()

    def play_range(self, start, end):
        if self.player is None:
            return
        self.range = (start, end)
        self.player.setPosition(int(start * 1000))
        self.player.play()

    def toggle(self):
        if self.player is None:
            return
        if self.player.playbackState() == self._QMP.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def seek_rel(self, sec):
        if self.player is None:
            return
        self.player.setPosition(max(0, self.player.position() + int(sec * 1000)))

    def set_loop(self, on):
        if self.player is None:
            return
        self.player.setLoops(-1 if on else 1)

    def pause(self):
        if self.player is not None:
            self.player.pause()

    def release(self):
        """تحرير الملف قبل نقله أو حذفه."""
        if self.player is None:
            return
        self.player.stop()
        self.player.setSource(QUrl())
