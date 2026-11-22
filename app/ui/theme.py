from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

C = {"bg": "#101318", "sidebar": "#171C24", "card": "#1D242E", "primary": "#3985F7", "success": "#28C76F",
     "warning": "#FFB020", "error": "#EA5455", "text": "#E6EAF0", "muted": "#8A94A6", "border": "#2A3340",
     "input": "#141A22"}

_ICONS = {
    "dashboard": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    "import": '<path d="M12 3v12m0 0l-4-4m4 4l4-4"/><path d="M4 17v3h16v-3"/>',
    "scenes": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/>',
    "export": '<path d="M12 15V3m0 0L8 7m4-4l4 4"/><path d="M4 17v3h16v-3"/>',
    "sorter": '<path d="M3 5h18l-7 8v6l-4-2v-4z"/>',
    "upload": '<path d="M7 18a4 4 0 010-8 5 5 0 019.6-1A4.5 4.5 0 0117 18"/><path d="M12 12v8m0-8l-3 3m3-3l3 3"/>',
    "workflow": '<circle cx="5" cy="6" r="2"/><circle cx="19" cy="12" r="2"/><circle cx="5" cy="18" r="2"/><path d="M7 6h5a3 3 0 013 3v1M7 18h5a3 3 0 003-3v-1"/>',
    "files": '<path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>',
    "projects": '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    "settings": '<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
    "log": '<path d="M5 6h14M5 12h14M5 18h9"/>',
}
_cache = {}


def icon(name: str, color: str = "#8A94A6", size: int = 22) -> QIcon:
    key = (name, color, size)
    if key not in _cache:
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
               f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{_ICONS[name]}</svg>')
        r = QSvgRenderer(QByteArray(svg.encode()))
        pm = QPixmap(size * 2, size * 2)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        r.render(p)
        p.end()
        _cache[key] = QIcon(pm)
    return _cache[key]


def stylesheet() -> str:
    c = C
    return f"""
* {{ font-family: "Helvetica Neue", "Geeza Pro", "Arial"; font-size: 13px; color: {c['text']}; }}
QMainWindow, QWidget#page, QDialog {{ background: {c['bg']}; }}
QWidget#sidebar {{ background: {c['sidebar']}; }}
QFrame#card {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 12px; }}
QLabel#h1 {{ font-size: 22px; font-weight: 700; }}
QLabel#h2 {{ font-size: 15px; font-weight: 600; }}
QLabel#muted {{ color: {c['muted']}; }}
QLabel#statValue {{ font-size: 24px; font-weight: 700; }}
QPushButton {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 7px 14px; }}
QPushButton:hover {{ border-color: {c['primary']}; }}
QPushButton:disabled {{ color: #566074; }}
QPushButton#primary {{ background: {c['primary']}; border: none; font-weight: 600; color: white; }}
QPushButton#primary:hover {{ background: #5598fa; }}
QPushButton#success {{ background: {c['success']}; border: none; color: #08130d; font-weight: 600; }}
QPushButton#warning {{ background: {c['warning']}; border: none; color: #1a1200; font-weight: 600; }}
QPushButton#danger {{ background: {c['error']}; border: none; color: white; font-weight: 600; }}
QPushButton#nav {{ background: transparent; border: none; text-align: start; padding: 11px 16px; border-radius: 10px; color: {c['muted']}; }}
QPushButton#nav:hover {{ background: #1f2733; }}
QPushButton#nav:checked {{ background: {c['primary']}; color: white; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{ background: {c['input']}; border: 1px solid {c['border']}; border-radius: 7px; padding: 5px 8px; selection-background-color: {c['primary']}; }}
QComboBox QAbstractItemView {{ background: {c['card']}; selection-background-color: {c['primary']}; }}
QTableWidget, QListWidget {{ background: {c['input']}; border: 1px solid {c['border']}; border-radius: 8px; gridline-color: {c['border']}; alternate-background-color: #171d26; }}
QHeaderView::section {{ background: {c['card']}; border: none; border-bottom: 1px solid {c['border']}; padding: 6px; color: {c['muted']}; }}
QTableWidget::item:selected, QListWidget::item:selected {{ background: {c['primary']}; }}
QProgressBar {{ background: {c['input']}; border: 1px solid {c['border']}; border-radius: 7px; text-align: center; height: 16px; }}
QProgressBar::chunk {{ background: {c['primary']}; border-radius: 6px; }}
QCheckBox {{ spacing: 8px; }}
QSlider::groove:horizontal {{ height: 5px; background: {c['border']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {c['primary']}; width: 14px; margin: -5px 0; border-radius: 7px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QToolTip {{ background: {c['card']}; border: 1px solid {c['border']}; }}
"""
