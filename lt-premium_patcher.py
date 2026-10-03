"""lt-premium_patcher.py — TelePatcher khusus Linux & Termux (lt = LinuxTermux).

Tidak bisa jalan di Windows (pakai premium_patcher.py untuk itu).

Dependensi: python3, apktool, openjdk-17+, apksigner (atau jarsigner), zipalign (opsional).

Install cepat:
  Termux : pkg install -y python apktool openjdk-17 apksigner
  Debian : sudo apt install -y python3 apktool openjdk-17-jre apksigner

Pakai:
  python3 lt-premium_patcher.py [--check] [--install-deps] [--decompile-only] [--build-only]
"""

import hashlib
import os
import platform
import shutil
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APK_NAME = "Telegram.apk"
DECOMPILE_DIR = os.path.join(BASE_DIR, "Decompile")
UNSIGNED_APK = os.path.join(BASE_DIR, "unsigned_tg.apk")
SIGNED_APK = os.path.join(BASE_DIR, "Telegram-Premium.apk")


def is_termux():
    return "com.termux" in os.environ.get("PREFIX", "") \
        or os.path.exists("/data/data/com.termux")


def is_windows():
    return os.name == "nt"


def find_apktool():
    path = shutil.which("apktool")
    if path:
        return path
    prefix = os.environ.get("PREFIX", "")
    for c in [os.path.join(prefix, "bin", "apktool") if prefix else None,
              "/usr/local/bin/apktool", "/usr/bin/apktool",
              os.path.expanduser("~/.local/bin/apktool")]:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def find_sdk_tool(name):
    """PATH dulu, lalu sisir direktori Android SDK umum."""
    path = shutil.which(name)
    if path:
        return path
    roots = []
    for env in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        if os.environ.get(env):
            roots.append(os.environ[env])
    roots += [os.path.expanduser("~/Android/Sdk"),
              "/opt/android-sdk", "/usr/lib/android-sdk"]
    cands = []
    for r in roots:
        bt = os.path.join(r, "build-tools")
        if os.path.isdir(bt):
            for ver in sorted(os.listdir(bt), reverse=True):
                p = os.path.join(bt, ver, name)
                if os.path.isfile(p) and os.access(p, os.X_OK):
                    cands.append(p)
    return cands[0] if cands else None


def pkg_manager():
    """Return 'pkg' (Termux native) or 'apt' (chroot/Linux), else None."""
    if shutil.which("pkg"):
        return "pkg"
    if shutil.which("apt"):
        return "apt"
    return None


def apktool_env():
    """Env untuk apktool: tambah -Xmx bila belum ada (smali Telegram rakus heap).

    Default -Xmx3g, override via TELEPATCH_XMX=4g. Menghormati _JAVA_OPTIONS
    yang sudah ada (mis. -Djava.net.preferIPv4Stack=true di chroot).
    """
    env = os.environ.copy()
    xmx = os.environ.get("TELEPATCH_XMX", "3g")
    cur = env.get("_JAVA_OPTIONS", "")
    if "-Xmx" not in cur:
        env["_JAVA_OPTIONS"] = f"{cur} -Xmx{xmx}".strip()
    return env


def install_deps():
    """Coba install dependensi otomatis (butuh pkg/apt + root di Linux)."""
    pm = pkg_manager()
    if pm == "pkg":
        pkgs = ["python", "apktool", "openjdk-17", "apksigner"]
        print("$ pkg install -y " + " ".join(pkgs))
        return subprocess.run(
            ["pkg", "install", "-y"] + pkgs).returncode == 0
    if pm == "apt":
        pkgs = ["python3", "apktool", "apksigner"]
        print("$ sudo apt install -y " + " ".join(pkgs))
        pre = [] if os.geteuid() == 0 else ["sudo"]
        r1 = subprocess.run(pre + ["apt", "update"])
        if r1.returncode != 0:
            return False
        return subprocess.run(
            pre + ["apt", "install", "-y"] + pkgs).returncode == 0
    print("FAIL: tidak ada pkg/apt. Install manual, lihat docstring.")
    return False


def check_deps():
    ok = True
    apktool = find_apktool()
    print(f"[{'OK' if apktool else 'FAIL'}] apktool -> {apktool or 'not found'}")
    ok &= bool(apktool)
    java = shutil.which("java")
    print(f"[{'OK' if java else 'FAIL'}] java -> {java or 'not found'}")
    ok &= bool(java)
    keytool = shutil.which("keytool")
    print(f"[{'OK' if keytool else 'FAIL'}] keytool -> {keytool or 'not found'}")
    ok &= bool(keytool)
    signer = find_sdk_tool("apksigner") or shutil.which("jarsigner")
    print(f"[{'OK' if signer else 'FAIL'}] signer -> {signer or 'not found'}")
    ok &= bool(signer)
    if not ok:
        if pkg_manager() == "pkg":
            print("  Install: pkg install -y python apktool openjdk-17 apksigner")
        else:
            print("  Install: apt install -y python3 apktool apksigner")
    return ok


def get_apk_sha256():
    apk = os.path.join(BASE_DIR, APK_NAME)
    if not os.path.exists(apk):
        print("FAIL Telegram.apk tidak ada.")
        return None
    keytool = shutil.which("keytool")
    if keytool:
        r = subprocess.run([keytool, "-printcert", "-jarfile", apk],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if "SHA256:" in line:
                    sha = line.split("SHA256:")[1].strip().replace(":", "")
                    print("SHA-256 value:", sha)
                    return sha
        print("WARN keytool gagal dibaca, lanjut tanpa SHA bypass.")
    else:
        print("WARN keytool tidak ada, lanjut tanpa SHA bypass.")
    return None


def decompile_apk():
    apk = os.path.join(BASE_DIR, APK_NAME)
    if not os.path.exists(apk):
        print("FAIL Telegram.apk tidak ada. Taruh dulu di folder ini.")
        if is_termux():
            print("  Misal: cp /storage/emulated/0/Download/Telegram.apk .")
            print("  (jalankan termux-setup-storage dulu bila belum)")
        return False
    apktool = find_apktool()
    if not apktool:
        print("FAIL apktool tidak ketemu.")
        return False
    if os.path.exists(DECOMPILE_DIR):
        shutil.rmtree(DECOMPILE_DIR)
    print("Decompiling (bisa 5-15 menit, jangan di-close)...")
    import time
    t0 = time.time()
    r = subprocess.run(
        [apktool, "d", "-r", apk, "-o", DECOMPILE_DIR],
        cwd=BASE_DIR, env=apktool_env())
    print(f"(selesai {time.time() - t0:.0f}s, exit={r.returncode})")
    if r.returncode == 0:
        print("OK APK decompiled -> 'Decompile/'")
        return True
    print("FAIL decompile gagal.")
    return False


def patch_smali(output_dir, sha256_value):
    target = None
    for root, _d, files in os.walk(output_dir):
        if "AndroidUtilities.smali" in files:
            target = os.path.join(root, "AndroidUtilities.smali")
            break
    if not target:
        print("FAIL AndroidUtilities.smali tidak ketemu.")
        return False
    with open(target, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        inside = False
        for line in lines:
            if ".method" in line and "getCertificateSHA256Fingerprint" in line:
                inside = True
                f.write(".method public static "
                        "getCertificateSHA256Fingerprint()Ljava/lang/String;\n")
                f.write("    .locals 1\n\n")
                f.write(f'    const-string v0, "{sha256_value or ""}"\n\n')
                f.write("    return-object v0\n")
                f.write(".end method\n")
            elif inside and ".end method" in line:
                inside = False
            elif not inside:
                f.write(line)
    print("OK AndroidUtilities.smali dipatch.")
    return True


def patch_is_premium(output_dir):
    target = None
    for root, _d, files in os.walk(output_dir):
        if "UserConfig.smali" in files:
            target = os.path.join(root, "UserConfig.smali")
            break
    if not target:
        print("FAIL UserConfig.smali tidak ketemu.")
        return False
    with open(target, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    found = False
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        inside = False
        for line in lines:
            if ".method" in line and "isPremium()Z" in line:
                inside = True
                found = True
                f.write(".method public isPremium()Z\n")
                f.write("    .locals 1\n\n")
                f.write("    const/4 v0, 0x1\n\n")
                f.write("    return v0\n")
                f.write(".end method\n")
                continue
            if inside:
                if ".end method" in line:
                    inside = False
                continue
            f.write(line)
    print("OK isPremium() -> selalu true." if found
          else "WARN isPremium() tidak ketemu.")
    return found


_jobs_supported = None


def apktool_supports_jobs(apktool):
    """Apktool Debian (2.7.0) tidak punya -j/--jobs; apktool 3.x punya."""
    global _jobs_supported
    if _jobs_supported is None:
        try:
            r = subprocess.run([apktool, "b", "--help"],
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            out = (r.stdout or "") + (r.stderr or "")
            _jobs_supported = "--jobs" in out or "-j" in out
        except Exception:
            _jobs_supported = False
    return _jobs_supported


def run_signer(unsigned_apk):
    keystore = os.path.join(BASE_DIR, "telepatch.keystore")
    alias, storepass = "telepatch", "telepatch"
    keytool = shutil.which("keytool")
    if not os.path.exists(keystore):
        if not keytool:
            print("FAIL keytool tidak ada, tidak bisa bikin keystore.")
            return False
        print("Bikin keystore baru...")
        r = subprocess.run(
            [keytool, "-genkeypair", "-keystore", keystore,
             "-alias", alias, "-keyalg", "RSA", "-keysize", "2048",
             "-validity", "10950", "-storepass", storepass,
             "-keypass", storepass, "-dname", "CN=TelePatcher"],
            capture_output=True, text=True)
        if r.returncode != 0:
            print("FAIL bikin keystore:", (r.stderr or r.stdout)[-2000:])
            return False
    aligned = unsigned_apk
    zipalign = find_sdk_tool("zipalign")
    if zipalign:
        aligned = os.path.join(BASE_DIR, "aligned.apk")
        subprocess.run([zipalign, "-p", "-f", "4", unsigned_apk, aligned],
                       capture_output=True)
    else:
        print("WARN zipalign tidak ada, lewati alignment.")
    apksigner = find_sdk_tool("apksigner")
    if apksigner:
        r = subprocess.run(
            [apksigner, "sign", "--ks", keystore,
             "--ks-pass", f"pass:{storepass}",
             "--out", SIGNED_APK, aligned],
            capture_output=True, text=True)
        if r.returncode == 0:
            print(f"OK signed -> {SIGNED_APK}")
            return True
        print("FAIL apksigner:", (r.stderr or r.stdout)[-2000:])
    jarsigner = shutil.which("jarsigner")
    if jarsigner:
        shutil.copy2(aligned, SIGNED_APK)
        r = subprocess.run(
            [jarsigner, "-sigalg", "SHA256withRSA", "-digestalg", "SHA-256",
             "-keystore", keystore, "-storepass", storepass,
             SIGNED_APK, alias],
            capture_output=True, text=True)
        if r.returncode == 0:
            print(f"OK signed (jarsigner) -> {SIGNED_APK}")
            return True
        print("FAIL jarsigner:", (r.stderr or r.stdout)[-2000:])
    print("FAIL tidak ada signer. Install apksigner.")
    return False


def build_apk():
    if not os.path.isdir(DECOMPILE_DIR):
        print("FAIL 'Decompile/' tidak ada, decode dulu.")
        return False
    apktool = find_apktool()
    if not apktool:
        print("FAIL apktool tidak ketemu.")
        return False
    print("Rebuilding (-j 1, bisa beberapa menit)...")
    import time
    t0 = time.time()
    # -j 1: job smali paralel suka race (NoSuchFileException acak).
    # Hanya bila apktool mendukung (3.x; apktool Debian 2.7 tidak punya).
    cmd = [apktool, "b", DECOMPILE_DIR]
    if apktool_supports_jobs(apktool):
        cmd += ["-j", "1"]
    r = subprocess.run(cmd, cwd=BASE_DIR, env=apktool_env())
    print(f"(selesai {time.time() - t0:.0f}s, exit={r.returncode})")
    if r.returncode != 0:
        print("FAIL build gagal.")
        return False
    print("OK APK rebuilt.")
    dist = os.path.join(DECOMPILE_DIR, "dist")
    cands = [os.path.join(dist, f) for f in os.listdir(dist)] \
        if os.path.isdir(dist) else []
    if not cands:
        print("FAIL hasil build tidak ketemu di Decompile/dist/.")
        return False
    shutil.copy2(cands[0], UNSIGNED_APK)
    print(f"OK disalin -> {UNSIGNED_APK}")
    run_signer(UNSIGNED_APK)
    return True


def main():
    import argparse
    if is_windows():
        sys.exit("Script ini khusus Linux/Termux. "
                 "Di Windows pakai premium_patcher.py")
    p = argparse.ArgumentParser(description="TelePatcher (Linux/Termux)")
    p.add_argument("--check", action="store_true")
    p.add_argument("--install-deps", action="store_true")
    p.add_argument("--decompile-only", action="store_true")
    p.add_argument("--build-only", action="store_true")
    args = p.parse_args()

    plat = "Termux" if is_termux() else f"{platform.system()}"
    print(f"TelePatcher-lt | {plat} {platform.machine()}")
    if args.install_deps:
        return 0 if install_deps() else 1
    if args.check:
        return 0 if check_deps() else 1
    if not check_deps():
        return 1
    if args.build_only:
        return 0 if build_apk() else 1
    apk = os.path.join(BASE_DIR, APK_NAME)
    if not os.path.exists(apk):
        print("FAIL Telegram.apk tidak ada di folder ini.")
        return 1
    print("OK Telegram.apk ketemu, lewati download.")
    sha = get_apk_sha256()
    if args.decompile_only:
        return 0 if decompile_apk() else 1
    if not decompile_apk():
        return 1
    patch_smali(DECOMPILE_DIR, sha)
    patch_is_premium(DECOMPILE_DIR)
    ok = build_apk()
    if ok and is_termux():
        print("Install di Termux: termux-open Telegram-Premium.apk")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
