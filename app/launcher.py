import subprocess
import sys
from pathlib import Path
from console_style import notice
from whs_asistent import read_config

APP = Path(__file__).resolve().parent


def run_child(command):
    with subprocess.Popen(command) as process:
        try:
            return process.wait()
        except KeyboardInterrupt:
            # Console Ctrl+C reaches the child too; let it close Edge cleanly.
            return process.wait()


def main():
    if not read_config()['instances']:
        notice('První spuštění – nastavení PIP')
        run_child([sys.executable, str(APP / "whs_asistent.py")])
        if not read_config()['instances']:
            notice('Nastavení nebylo dokončeno. Spusťte WHS Asistenta znovu.', 'warning')
            return
    while True:
        notice("\nWHS ASISTENT")
        print("1 - Zpracovat WHS objednávky\n2 - Kontrola bez zmen\nCtrl+C - Ukoncit")
        choice = input("Vyberte: ").strip()
        if choice not in ("1", "2"):
            continue
        command = [sys.executable, str(APP / "pip_tool.py")]
        if choice == "1":
            command.append("--execute")
        run_child(command)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nUkonceno.")
    except (ValueError, OSError):
        notice('Konfiguraci nelze načíst. Opravte data/config.json; soubor nebyl změněn.', 'error')
        raise SystemExit(1)
