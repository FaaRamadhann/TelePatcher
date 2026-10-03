"""TelePatcher - Telegram Premium patcher (Windows / Linux / Termux)."""
import hashlib
import os
import platform
import shutil
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APK_NAME = "Telegram.apk"
DECOMPILE_DIR = os.path.join(BASE_DIR, "Decompile")
UNSIGNED_APK = os.path.join(BASE_DIR, "unsigned_tg.apk")
SIGNED_APK = os.path.join(BASE_DIR, "Telegram-Premium.apk")


def is_windows():
    return os.name == "nt" or platform.system().lower() == "windows"


def is_termux():
    return "com.termux" in os.environ.get("PREFIX", "") or os.path.exists("/data/data/com.termux")


def is_linux():
    return platform.system().lower() == "linux"


def find_sdk_tool(name):
    """Find Android SDK build-tools binary: PATH first, then common SDK dirs.
    (Pattern borrowed from ex-build.py: explicit SDK paths beat PATH.)"""
    path = shutil.which(name)
    if path:
        return path
    exe = name + ".exe" if is_windows() else name
    bat = name + ".bat" if is_windows() else name
    roots = []
    for env in ("ANDROID_SDK_ROOT", "ANDROID_HOME", "ANDROID_SDK_HOME"):
        if os.environ.get(env):
            roots.append(os.environ[env])
    roots += [
        os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk"),
        r"C:\AndroidSDK",
        r"C:\Android\Sdk",
        os.path.expanduser("~/Android/Sdk"),
        "/opt/android-sdk",
        "/usr/lib/android-sdk",
    ]
    cands = []
    for r in roots:
        bt = os.path.join(r, "build-tools")
        if os.path.isdir(bt):
            for ver in sorted(os.listdir(bt), reverse=True):
                for fn in (bat, exe):
                    p = os.path.join(bt, ver, fn)
                    if os.path.exists(p):
                        cands.append(p)
    # versioned dirs sorted desc -> newest first
    return cands[0] if cands else None


LOCK_FILE = os.path.join(BASE_DIR, ".telepatch.lock")


def acquire_lock():
    """Cegah dua instance jalan bareng (rebutan folder Decompile/)."""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE) as f:
                pid = f.read().strip()
            print(f"FAIL proses lain sedang jalan (pid {pid}). Tunggu selesai dulu,")
            print("     atau hapus .telepatch.lock bila yakin tidak ada proses lain.")
        except Exception:
            print("FAIL proses lain sedang jalan. Tunggu selesai dulu.")
        return False
    try:
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
        return True
    except Exception as e:
        print("FAIL tidak bisa bikin lock file:", e)
        return False


def release_lock():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception:
        pass


def clean_dir(path, retries=5):
    """rmtree yang tahan file-lock Windows (coba ulang + onerror)."""
    import time
    import stat

    def onerror(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass

    for i in range(retries):
        try:
            if os.path.exists(path):
                shutil.rmtree(path, onerror=onerror)
            return True
        except OSError:
            if i == retries - 1:
                print(f"FAIL tidak bisa hapus '{path}': dipakai proses lain?")
                print("     Tutup proses TelePatcher lain lalu coba lagi.")
                return False
            time.sleep(2)
    return False


def find_apktool():
    """Find apktool. Handles Windows apktool.bat which needs shell=True."""
    path = shutil.which("apktool")
    if path:
        return path
    # Common manual install locations
    candidates = [
        r"C:\apktool\apktool.bat",
        r"C:\apktool\apktool.jar",
        "/usr/local/bin/apktool",
        "/usr/bin/apktool",
        os.path.expanduser("~/apktool/apktool.jar"),
        os.path.join(os.environ.get("PREFIX", ""), "bin", "apktool"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def resolve_apktool_cmd(args):
    """Prefer `java -jar apktool.jar`: avoids .bat `pause` and lost exit codes."""
    apktool = find_apktool()
    if apktool is None:
        return None, False
    if apktool.endswith(".jar"):
        return ["java", "-jar", apktool] + args, False
    sibling = os.path.join(os.path.dirname(apktool), "apktool.jar")
    if os.path.exists(sibling):
        return ["java", "-jar", sibling] + args, False
    if is_windows():
        return [apktool] + args, True
    return [apktool] + args, False


def run_apktool_live(args):
    """Run apktool streaming output live (for long ops like decompile/build)."""
    cmd_shell = resolve_apktool_cmd(args)
    if cmd_shell[0] is None:
        return None
    cmd, shell = cmd_shell
    import time
    start = time.time()
    print(f"$ {' '.join(cmd)}")
    try:
        # stdin=DEVNULL: .bat ends with `pause`; EOF lets it continue
        # instead of waiting for a keypress.
        result = subprocess.run(cmd, shell=shell, cwd=BASE_DIR,
                                stdin=subprocess.DEVNULL)
        print(f"(done in {time.time() - start:.0f}s, exit={result.returncode})")
        return result
    except FileNotFoundError:
        return None


def run_apktool(args):
    """Run apktool cross-platform. Returns CompletedProcess."""
    cmd_shell = resolve_apktool_cmd(args)
    if cmd_shell[0] is None:
        return None
    cmd, shell = cmd_shell
    if shell:
        return subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", shell=True)
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def check_deps():
    ok = True
    apktool = find_apktool()
    if apktool:
        print(f"[OK] apktool -> {apktool}")
    else:
        ok = False
        print("[FAIL] apktool not found.")
        if is_windows():
            print("  Install: download apktool.bat + apktool.jar from https://ibotpeaches.github.io/Apktool/")
            print("  Put both in C:\\apktool\\ and add C:\\apktool to PATH.")
            print("  Or: winget install -e --id iBotPeaches.Apktool")
        elif is_termux():
            print("  Install: pkg install -y apktool openjdk-17")
        else:
            print("  Install: sudo apt install -y apktool openjdk-17-jre")
    java = shutil.which("java")
    print(f"[{'OK' if java else 'FAIL'}] java -> {java or 'not found, install JDK 17+'}")
    if not java:
        ok = False
    return ok


def download_telegram_apk():
    apk = os.path.join(BASE_DIR, APK_NAME)
    if os.path.exists(apk):
        print("OK Telegram.apk already exists, skipping download.")
        return True
    print("FAIL Telegram.apk not found. Place Telegram.apk next to this script first.")
    return False


def get_apk_sha256():
    apk = os.path.join(BASE_DIR, APK_NAME)
    if not os.path.exists(apk):
        print("FAIL Telegram.apk not found, cannot get SHA-256.")
        return None
    # Prefer pure-python: cert SHA256 via keytool if available, else apk cert hash fallback
    keytool = shutil.which("keytool")
    if keytool:
        try:
            if is_windows():
                result = subprocess.run(
                    [keytool, "-printcert", "-jarfile", apk],
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace", shell=False)
            else:
                result = subprocess.run(
                    ["keytool", "-printcert", "-jarfile", apk],
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace")
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "SHA256:" in line:
                        sha = line.split("SHA256:")[1].strip().replace(":", "")
                        print("SHA-256 value:", sha)
                        return sha
            print("WARN keytool output unreadable, fallback to file hash.")
        except FileNotFoundError:
            print("WARN keytool executable not found.")
    # Fallback: SHA-256 of file (keeps pipeline running)
    h = hashlib.sha256()
    with open(apk, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    print("SHA-256 (file hash fallback):", h.hexdigest())
    return None


def decompile_apk():
    apk = os.path.join(BASE_DIR, APK_NAME)
    if not os.path.exists(apk):
        print("FAIL Telegram.apk not found, cannot decompile.")
        return False
    if find_apktool() is None:
        print("FAIL apktool not found.")
        check_deps()
        return False
    if os.path.exists(DECOMPILE_DIR):
        if not clean_dir(DECOMPILE_DIR):
            return False
    print("Decompiling FULL (resource ikut di-decode, bisa 10-20 menit)...")
    result = run_apktool_live(["d", apk, "-o", DECOMPILE_DIR])
    if result is None:
        print("FAIL apktool executable not found.")
        return False
    if result.returncode == 0:
        print("OK APK decompiled -> 'Decompile/'")
        return True
    print("FAIL Decompilation failed:", result.stderr or result.stdout)
    return False


def edit_smali_file(output_dir, sha256_value):
    target = None
    for root, _dirs, files in os.walk(output_dir):
        if "AndroidUtilities.smali" in files:
            target = os.path.join(root, "AndroidUtilities.smali")
            break
    if not target:
        print("FAIL AndroidUtilities.smali not found.")
        return False
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        with open(target, "w", encoding="utf-8", newline="\n") as f:
            inside = False
            for line in lines:
                if ".method" in line and "getCertificateSHA256Fingerprint" in line:
                    inside = True
                    f.write(".method public static getCertificateSHA256Fingerprint()Ljava/lang/String;\n")
                    f.write("    .locals 1\n\n")
                    if sha256_value:
                        f.write(f'    const-string v0, "{sha256_value}"\n\n')
                    else:
                        f.write('    const-string v0, ""\n\n')
                    f.write("    return-object v0\n")
                    f.write(".end method\n")
                elif inside and ".end method" in line:
                    inside = False
                elif not inside:
                    f.write(line)
        print("OK AndroidUtilities.smali modified.")
        return True
    except Exception as e:
        print("FAIL edit AndroidUtilities.smali:", e)
        return False


def patch_premium_self(output_dir):
    """Force checkPremiumSelf lambdas to report premium=true.

    Server mengisi TLRPC$User.premium=false untuk akun gratis, lalu
    UserConfig.checkPremiumSelf -> MessagesController.updatePremium(false)
    me-reset state premium internal. Timpa pembacaan field dengan const true.
    """
    target = None
    for root, _dirs, files in os.walk(output_dir):
        if "UserConfig.smali" in files:
            p = os.path.join(root, "UserConfig.smali")
            if "org/telegram/messenger/UserConfig.smali" in p.replace("\\", "/"):
                target = p
                break
    if not target:
        print("FAIL UserConfig.smali (messenger) not found.")
        return False
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        patched = 0
        out = []
        cur_method = ""
        for line in lines:
            s = line.strip()
            if s.startswith(".method"):
                cur_method = s
            elif s.startswith(".end method"):
                cur_method = ""
            if ("checkPremiumSelf" in cur_method
                    and s.startswith("iget-boolean p1, p1,")
                    and "TLRPC$User;->premium:Z" in s):
                indent = line[:len(line) - len(line.lstrip())]
                out.append(f"{indent}const/4 p1, 0x1\n")
                patched += 1
                continue
            out.append(line)
        if patched:
            with open(target, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(out)
            print(f"OK checkPremiumSelf dipaksa premium=true ({patched} lokasi).")
            return True
        print("WARN pola checkPremiumSelf tidak ketemu, mungkin versi beda.")
        return False
    except Exception as e:
        print("FAIL patch checkPremiumSelf:", e)
        return False


def patch_current_user_premium(output_dir):
    """Set currentUser.premium=true di getCurrentUser().

    Banyak UI (badge profil, isPremiumUser) baca field TLRPC$User.premium
    langsung dari objek user, bukan via isPremium(). Paksa true tiap
    getCurrentUser() dipanggil (null-safe, pakai register v2 baru).
    """
    target = None
    for root, _dirs, files in os.walk(output_dir):
        if "UserConfig.smali" in files:
            p = os.path.join(root, "UserConfig.smali")
            if "org/telegram/messenger/UserConfig.smali" in p.replace("\\", "/"):
                target = p
                break
    if not target:
        print("FAIL UserConfig.smali (messenger) not found.")
        return False
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        method_sig = ".method public getCurrentUser()Lorg/telegram/tgnet/TLRPC$User;"
        if method_sig not in text:
            print("WARN getCurrentUser() tidak ketemu.")
            return False
        if "cond_premium_forced_telepatch" in text:
            print("OK currentUser.premium patch sudah ada, lewati.")
            return True
        start = text.index(method_sig)
        end = text.index(".end method", start)
        body = text[start:end]
        if ".locals 2" not in body:
            print("WARN struktur getCurrentUser() beda dari harapan.")
            return False
        body = body.replace(".locals 2", ".locals 3", 1)
        anchor = ("iget-object v1, p0, "
                  "Lorg/telegram/messenger/UserConfig;->currentUser:"
                  "Lorg/telegram/tgnet/TLRPC$User;")
        if anchor not in body:
            print("WARN anchor getCurrentUser() tidak ketemu.")
            return False
        inject = (anchor +
                  "\n    if-eqz v1, :cond_premium_forced_telepatch"
                  "\n    const/4 v2, 0x1"
                  "\n    iput-boolean v2, v1, "
                  "Lorg/telegram/tgnet/TLRPC$User;->premium:Z"
                  "\n    :cond_premium_forced_telepatch")
        body = body.replace(anchor, inject, 1)
        text = text[:start] + body + text[end:]
        with open(target, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("OK getCurrentUser() selalu laporkan premium=true.")
        return True
    except Exception as e:
        print("FAIL patch currentUser.premium:", e)
        return False


def patch_is_premium_user_self(output_dir):
    """isPremiumUser(user) true bila user adalah akun sendiri.

    Objek User di cache MessagesController (bukan currentUser) field
    premium-nya false dari server. Bandingkan user.id vs clientUserId;
    cocok -> premium. Logika lama (premium && bukan support) dipertahankan.
    """
    target = None
    for root, _dirs, files in os.walk(output_dir):
        if "MessagesController.smali" in files:
            p = os.path.join(root, "MessagesController.smali")
            if "org/telegram/messenger/MessagesController.smali" in p.replace("\\", "/"):
                target = p
                break
    if not target:
        print("FAIL MessagesController.smali not found.")
        return False
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        sig = (".method public isPremiumUser"
               "(Lorg/telegram/tgnet/TLRPC$User;)Z")
        if sig not in text:
            print("WARN isPremiumUser() tidak ketemu.")
            return False
        if "cond_self_premium_telepatch" in text:
            print("OK isPremiumUser self-patch sudah ada, lewati.")
            return True
        start = text.index(sig)
        end = text.index(".end method", start)
        new_body = (
            sig + "\n"
            "    .locals 4\n"
            "\n"
            "    if-eqz p1, :cond_0\n"
            "\n"
            "    iget-boolean v0, p1, Lorg/telegram/tgnet/TLRPC$User;->premium:Z\n"
            "\n"
            "    if-eqz v0, :check_self_premium_telepatch\n"
            "\n"
            "    invoke-static {p1}, Lorg/telegram/messenger/MessagesController;->isSupportUser(Lorg/telegram/tgnet/TLRPC$User;)Z\n"
            "\n"
            "    move-result p1\n"
            "\n"
            "    if-nez p1, :cond_0\n"
            "\n"
            "    const/4 p1, 0x1\n"
            "\n"
            "    return p1\n"
            "\n"
            "    :check_self_premium_telepatch\n"
            "    iget-wide v0, p1, Lorg/telegram/tgnet/TLRPC$User;->id:J\n"
            "\n"
            "    iget v2, p0, Lorg/telegram/messenger/BaseController;->currentAccount:I\n"
            "\n"
            "    invoke-static {v2}, Lorg/telegram/messenger/UserConfig;->getInstance(I)Lorg/telegram/messenger/UserConfig;\n"
            "\n"
            "    move-result-object v2\n"
            "\n"
            "    invoke-virtual {v2}, Lorg/telegram/messenger/UserConfig;->getClientUserId()J\n"
            "\n"
            "    move-result-wide v2\n"
            "\n"
            "    cmp-long v0, v0, v2\n"
            "\n"
            "    if-nez v0, :cond_0\n"
            "\n"
            "    const/4 p1, 0x1\n"
            "\n"
            "    return p1\n"
            "\n"
            "    :cond_0\n"
            "    const/4 p1, 0x0\n"
            "\n"
            "    return p1\n"
        )
        text = text[:start] + new_body + text[end:]
        with open(target, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("OK isPremiumUser() true untuk akun sendiri.")
        return True
    except Exception as e:
        print("FAIL patch isPremiumUser:", e)
        return False


def replace_ispremium_with_constant_true(output_dir):
    target = None
    for root, _dirs, files in os.walk(output_dir):
        if "UserConfig.smali" in files:
            target = os.path.join(root, "UserConfig.smali")
            break
    if not target:
        print("FAIL UserConfig.smali not found.")
        return False
    try:
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
        if found:
            print("OK isPremium() overridden to always return true.")
        else:
            print("WARN isPremium() not found, no changes made.")
        return found
    except Exception as e:
        print("FAIL error:", e)
        return False


def run_cmd(cmd):
    """Run a SDK tool command; shell=True on Windows for .bat wrappers."""
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          shell=is_windows())


def run_signer(unsigned_apk):
    """Sign APK cross-platform: apksigner > jarsigner > legacy signer.sh."""
    keystore = os.path.join(BASE_DIR, "telepatch.keystore")
    alias, storepass, keypass = "telepatch", "telepatch", "telepatch"
    if not os.path.exists(keystore):
        keytool = shutil.which("keytool")
        if not keytool:
            print("FAIL keytool not found, cannot create keystore.")
            return False
        print("Generating debug keystore...")
        r = subprocess.run(
            [keytool, "-genkeypair", "-v", "-keystore", keystore,
             "-alias", alias, "-keyalg", "RSA", "-keysize", "2048",
             "-validity", "10950", "-storepass", storepass,
             "-keypass", keypass, "-dname", "CN=TelePatcher"],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            print("FAIL keystore creation:", r.stderr or r.stdout)
            return False
    # zipalign if available (PATH or explicit SDK build-tools dir)
    aligned = unsigned_apk
    zipalign = find_sdk_tool("zipalign")
    if zipalign:
        aligned = os.path.join(BASE_DIR, "aligned.apk")
        subprocess.run([zipalign, "-p", "-f", "4", unsigned_apk, aligned],
                       capture_output=True)
    else:
        print("WARN zipalign not found, skipping alignment.")
    apksigner = find_sdk_tool("apksigner")
    if apksigner:
        r = run_cmd(
            [apksigner, "sign", "--ks", keystore, "--ks-pass",
             f"pass:{storepass}", "--out", SIGNED_APK, aligned])
        if r.returncode == 0:
            print(f"OK signed -> {SIGNED_APK}")
            return True
        print("FAIL apksigner:", r.stderr or r.stdout)
    jarsigner = shutil.which("jarsigner")
    if jarsigner:
        shutil.copy2(aligned, SIGNED_APK)
        r = subprocess.run(
            [jarsigner, "-verbose", "-sigalg", "SHA256withRSA",
             "-digestalg", "SHA-256", "-keystore", keystore,
             "-storepass", storepass, SIGNED_APK, alias],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode == 0:
            print(f"OK signed (jarsigner) -> {SIGNED_APK}")
            return True
        print("FAIL jarsigner:", r.stderr or r.stdout)
    # legacy signer.sh fallback (linux/termux/git-bash)
    signer_sh = os.path.join(BASE_DIR, "signer.sh")
    if os.path.exists(signer_sh):
        bash = shutil.which("bash")
        if bash:
            try:
                subprocess.run([bash, signer_sh], check=True, cwd=BASE_DIR)
                print("OK signed with signer.sh.")
                return True
            except subprocess.CalledProcessError as e:
                print("FAIL signer.sh:", e)
        else:
            print("FAIL bash not found, cannot run signer.sh.")
    print("FAIL no signer available. Install Android build-tools (apksigner).")
    return False


def apktool_supports_jobs(apktool_cmd):
    """Apktool Debian (2.7.0) tidak punya -j/--jobs; apktool 3.x punya."""
    try:
        r = subprocess.run(apktool_cmd + ["b", "--help"],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        return "--jobs" in out
    except Exception:
        return False


def build_apk():
    if not os.path.isdir(DECOMPILE_DIR):
        print("FAIL 'Decompile/' not found, run decompile first.")
        return False
    if find_apktool() is None:
        print("FAIL apktool not found, cannot rebuild.")
        return False
    print("Rebuilding (bisa beberapa menit)...")
    # NOTE: `-r/--no-res` is a *decode* option only; `apktool b` rejects it.
    # `-j 1`: parallel smali jobs race on Windows (random NoSuchFileException).
    # Only if supported (apktool 3.x; Debian's 2.7 lacks it).
    build_cmd = ["b", "Decompile"]
    probe_cmd, _ = resolve_apktool_cmd([])
    if probe_cmd and probe_cmd[0] == "java" and apktool_supports_jobs(probe_cmd):
        build_cmd += ["-j", "1"]
    result = run_apktool_live(build_cmd)
    if result is None:
        print("FAIL apktool executable not found.")
        return False
    if result.returncode != 0:
        print(f"FAIL build (exit={result.returncode}).")
        return False
    print("OK APK rebuilt.")
    built = os.path.join(DECOMPILE_DIR, "dist", "Telegram.apk")
    if not os.path.exists(built):
        # apktool may keep original name differently; search dist/
        dist = os.path.join(DECOMPILE_DIR, "dist")
        cands = [os.path.join(dist, f) for f in os.listdir(dist)] if os.path.isdir(dist) else []
        built = cands[0] if cands else built
    if os.path.exists(built):
        shutil.copy2(built, UNSIGNED_APK)
        print(f"OK copied as {UNSIGNED_APK}")
        run_signer(UNSIGNED_APK)
        return True
    print("FAIL rebuilt APK not found.")
    return False


def main():
    import argparse
    p = argparse.ArgumentParser(description="TelePatcher - Telegram Premium patcher")
    p.add_argument("--check", action="store_true", help="only check dependencies")
    p.add_argument("--decompile-only", action="store_true")
    p.add_argument("--build-only", action="store_true")
    args = p.parse_args()

    print(f"TelePatcher | {platform.system()} {platform.machine()} | Termux={is_termux()}")
    if not acquire_lock():
        return 1
    try:
        return _main(args)
    finally:
        release_lock()


def _main(args):
    if args.check:
        return 0 if check_deps() else 1
    if not check_deps():
        return 1
    if args.build_only:
        return 0 if build_apk() else 1
    if not download_telegram_apk():
        return 1
    sha = get_apk_sha256()
    if args.decompile_only:
        return 0 if decompile_apk() else 1
    if not decompile_apk():
        return 1
    if sha:
        edit_smali_file(DECOMPILE_DIR, sha)
    else:
        print("WARN skipping SHA bypass value (still patches isPremium).")
    replace_ispremium_with_constant_true(DECOMPILE_DIR)
    patch_premium_self(DECOMPILE_DIR)
    patch_current_user_premium(DECOMPILE_DIR)
    patch_is_premium_user_self(DECOMPILE_DIR)
    return 0 if build_apk() else 1


if __name__ == "__main__":
    raise SystemExit(main())
