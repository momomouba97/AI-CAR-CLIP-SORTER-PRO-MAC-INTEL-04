# -*- mode: python ; coding: utf-8 -*-
# إعدادات بناء PyInstaller لتطبيق macOS Intel (x86_64)
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

APP_NAME = "AI CAR CLIP SORTER PRO"
datas = [("assets/icon.png", "assets")]
if os.path.exists("assets/bin/ffmpeg"):
    datas.append(("assets/bin/ffmpeg", "bin"))
else:
    raise SystemExit("assets/bin/ffmpeg is missing: run scripts/prepare_ffmpeg.py first")
datas += collect_data_files("googleapiclient")          # وثائق الاكتشاف الثابتة
for pkg in ("keyring", "google-api-python-client", "google-auth", "google-auth-oauthlib", "scenedetect"):
    try:
        datas += copy_metadata(pkg)                       # keyring يكتشف الـ backends عبر entry points
    except Exception:
        pass
for pkg in ("importlib_metadata", "jaraco.classes", "jaraco.functools", "jaraco.context", "more_itertools"):
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass

hidden = (collect_submodules("keyring") + collect_submodules("scenedetect") +
          collect_submodules("googleapiclient") + collect_submodules("google_auth_oauthlib") +
          ["keyring.backends.macOS", "PySide6.QtSvg", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets"])

a = Analysis(["main.py"], pathex=["."], datas=datas, hiddenimports=hidden,
             excludes=["tkinter", "matplotlib", "scipy", "pandas", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
                       "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtDesigner", "PySide6.QtCharts"],
             noarchive=False)

# مزوّد OpenSSL القديم (legacy.dylib) سُحب من الـ Runner ويتطلب macOS 15، ولا يحتاجه التطبيق
# (الاتصال الآمن يعمل بالمزوّد الافتراضي المدمج في libcrypto). نستبعده ليبقى التطبيق متوافقاً مع Big Sur.
def _keep(item):
    return "ossl-modules" not in str(item[0]) and "ossl-modules" not in str(item[1])


a.binaries = [i for i in a.binaries if _keep(i)]
a.datas = [i for i in a.datas if _keep(i)]

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="AICarClipSorterPro", console=False,
          target_arch="x86_64", codesign_identity=None, entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="AICarClipSorterPro")
app = BUNDLE(coll, name=APP_NAME + ".app",
             icon="assets/icon.icns" if os.path.exists("assets/icon.icns") else None,
             bundle_identifier="com.aiccs.carclipsorterpro",
             info_plist={"CFBundleName": APP_NAME, "CFBundleDisplayName": APP_NAME,
                         "CFBundleShortVersionString": "1.0.0", "CFBundleVersion": "1.0.0",
                         "LSMinimumSystemVersion": "11.0", "NSHighResolutionCapable": True,
                         "NSRequiresAquaSystemAppearance": False,
                         "NSHumanReadableCopyright": "MIT License"})
