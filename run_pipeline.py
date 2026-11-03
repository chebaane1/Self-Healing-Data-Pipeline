import os
import shutil
import subprocess
import sys
import sysconfig
import traceback
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
ERROR_LOG_PATH = PROJECT_ROOT / "error_logs.txt"

def find_dbt_executable():
    configured_executable = os.environ.get("DBT_EXECUTABLE")
    if configured_executable:
        return configured_executable

    scripts_directory = Path(sysconfig.get_path("scripts"))
    executable_names = ["dbt.exe", "dbt"] if os.name == "nt" else ["dbt"]
    for executable_name in executable_names:
        candidate = scripts_directory / executable_name
        if candidate.is_file():
            return str(candidate)

    return shutil.which("dbt") or "dbt"


def build_commands():
    dbt_executable = find_dbt_executable()
    return [
        [sys.executable, "scripts/init_source.py"],
        [dbt_executable, "run", "--profiles-dir", "."],
        [dbt_executable, "test", "--profiles-dir", "."],
    ]


def save_failure(command, stdout, stderr, stacktrace):
    diagnostic = (
        f"Failed command: {' '.join(command)}\n\n"
        f"Python traceback:\n{stacktrace}\n"
        f"stdout:\n{stdout or '(empty)'}\n\n"
        f"stderr:\n{stderr or '(empty)'}\n"
    )
    ERROR_LOG_PATH.write_text(diagnostic, encoding="utf-8")


def main():
    for command in build_commands():
        print(f"\n$ {' '.join(command)}")

        try:
            result = subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as error:
            stacktrace = traceback.format_exc()
            stdout = error.stdout or ""
            stderr = error.stderr or ""
            save_failure(command, stdout, stderr, stacktrace)

            if stdout:
                print(stdout, end="")
            if stderr:
                print(stderr, end="", file=sys.stderr)
            print(
                f"\nPipeline échoué (code {error.returncode}). "
                f"Diagnostic complet : {ERROR_LOG_PATH}"
            )
            return error.returncode or 1
        except Exception:
            stacktrace = traceback.format_exc()
            save_failure(command, "", "", stacktrace)
            print(
                f"\nPipeline échoué pendant le lancement de la commande. "
                f"Diagnostic complet : {ERROR_LOG_PATH}"
            )
            return 1

        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)

    print("\nPipeline réussi : toutes les commandes ont abouti.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())