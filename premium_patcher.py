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


def run_apktool(args):
    """Run apktool cross-platform. Returns CompletedProcess."""
    apktool = find_apktool()
    if apktool is None:
        return None
    if apktool.endswith(".jar"):
        cmd = ["java", "-jar", apktool] + args
        return subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    if is_windows():
        # .bat/.cmd cannot be exec'd directly without shell -> use cmd /c
        cmd = [apktool] + args
        return subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", shell=True)
    return subprocess.run([apktool] + args, capture_output=True, text=True,
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
        shutil.rmtree(DECOMPILE_DIR)
    print("Decompiling...")
    result = run_apktool(["d", "-r", apk, "-o", DECOMPILE_DIR])
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
    # zipalign if available
    aligned = unsigned_apk
    zipalign = shutil.which("zipalign")
    if zipalign:
        aligned = os.path.join(BASE_DIR, "aligned.apk")
        subprocess.run([zipalign, "-p", "-f", "4", unsigned_apk, aligned],
                       capture_output=True)
    else:
        print("WARN zipalign not found, skipping alignment.")
    apksigner = shutil.which("apksigner")
    if apksigner:
        r = subprocess.run(
            [apksigner, "sign", "--ks", keystore, "--ks-pass",
             f"pass:{storepass}", "--out", SIGNED_APK, aligned],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
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


def build_apk():
    if not os.path.isdir(DECOMPILE_DIR):
        print("FAIL 'Decompile/' not found, run decompile first.")
        return False
    if find_apktool() is None:
        print("FAIL apktool not found, cannot rebuild.")
        return False
    result = run_apktool(["b", "Decompile", "-r"])
    if result is None:
        print("FAIL apktool executable not found.")
        return False
    if result.returncode != 0:
        print("FAIL build:", result.stderr or result.stdout)
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
    return 0 if build_apk() else 1


if __name__ == "__main__":
    raise SystemExit(main())
