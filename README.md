# TelePatcher

Patcher Telegram APK: bypass `getCertificateSHA256Fingerprint` + override `UserConfig.isPremium()` agar selalu `true`. Support **Windows, Linux, dan Termux (Android)**.

> Untuk edukasi / modifikasi APK milik sendiri. Hormati TOS Telegram.

## Fitur
- Deteksi `apktool` lintas platform (termasuk `C:\apktool\apktool.bat` di Windows yang butuh `shell=True` — ini penyebab error `apktool executable not found` padahal `where apktool` ketemu).
- Ambil SHA-256 cert via `keytool`, fallback hash file.
- Decompile (`apktool d -r`), patch smali, rebuild (`apktool b`), sign otomatis (`apksigner` → `jarsigner` → `signer.sh`).
- CLI: `--check`, `--decompile-only`, `--build-only`.

## Prasyarat
| OS | Install |
|----|---------|
| Windows | `winget install -e --id iBotPeaches.Apktool` + JDK 17 (`winget install -e --id EclipseAdoptium.Temurin.17.JRE`). Atau manual: taruh `apktool.bat` + `apktool.jar` di `C:\apktool`, tambahkan ke PATH. Butuh juga Android build-tools (`apksigner`, `zipalign`) atau JDK (`jarsigner`, `keytool`). |
| Linux (Debian/Ubuntu) | `sudo apt install -y apktool openjdk-17-jre apksigner` (atau `android-sdk-build-tools`) |
| Termux | `pkg install -y apktool openjdk-17` |

Verifikasi:
```
python premium_patcher.py --check
apktool --version
java -version
```

## Cara Pakai
1. Taruh `Telegram.apk` di folder ini (sejajar `premium_patcher.py`).
2. Jalankan:
```
# Windows
py premium_patcher.py
# Linux / Termux
python3 premium_patcher.py
```
3. Hasil:
   - `unsigned_tg.apk` — hasil rebuild belum signed
   - `Telegram-Premium.apk` — hasil signed, siap install
   - `Decompile/` — hasil decompile + smali yang dipatch

Opsi:
```
python premium_patcher.py --check           # cek dependensi saja
python premium_patcher.py --decompile-only  # hanya decompile
python premium_patcher.py --build-only      # rebuild + sign dari Decompile/
```

## Fix error `apktool executable not found` (Windows)
Gejala: `where apktool` → `C:\apktool\apktool.bat` ketemu, tapi script tetap error.
Penyebab: `subprocess.run(["apktool", ...])` tanpa `shell=True` tidak bisa mengeksekusi file `.bat`.
Solusi di versi ini (`premium_patcher.py:run_apktool`): di Windows dijalankan dengan `shell=True` dan path hasil `shutil.which("apktool")` / fallback `C:\apktool\apktool.bat`. Sudah dites: `apktool --version` → `3.0.3`.

## Struktur
```
TelePatcher/
├── premium_patcher.py
├── Telegram.apk            # sediakan sendiri, jangan di-commit
├── Decompile/              # hasil decompile (git-ignored)
├── unsigned_tg.apk         # git-ignored
├── Telegram-Premium.apk    # git-ignored
├── LICENSE (MIT)
└── README.md
```

## Buat repo GitHub `TelePatcher` di akun FaaRamadhann
Saya tidak bisa push ke GitHub kamu tanpa akses/token, jadi jalankan ini (Windows PowerShell):

```powershell
cd D:\Faa-Tools\TelegramPatch
git init
git add premium_patcher.py README.md LICENSE .gitignore
git commit -m "feat: TelePatcher cross-platform (win/linux/termux) + apktool.bat fix"
gh repo create FaaRamadhann/TelePatcher --public --source=. --push
# tanpa gh CLI:
# 1. buat repo kosong "TelePatcher" di github.com/FaaRamadhann
# 2. git remote add origin https://github.com/FaaRamadhann/TelePatcher.git
# 3. git branch -M main; git push -u origin main
```

## Lisensi
MIT — lihat [LICENSE](LICENSE).
