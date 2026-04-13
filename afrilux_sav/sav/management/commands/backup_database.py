from datetime import datetime
import os
from pathlib import Path
import shutil
import subprocess

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Realise une sauvegarde horodatee de la base de donnees, compatible SQLite et PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", default="")
        parser.add_argument("--format", choices=["auto", "custom", "plain"], default="auto")

    def _backup_sqlite(self, db_config, output_dir: Path):
        db_path = Path(db_config["NAME"])
        if not db_path.exists():
            raise CommandError(f"Base introuvable: {db_path}")

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = output_dir / f"{db_path.stem}-{timestamp}{db_path.suffix}"
        shutil.copy2(db_path, target)
        return target

    def _backup_postgresql(self, db_config, output_dir: Path, requested_format: str):
        db_name = str(db_config.get("NAME", "")).strip()
        if not db_name:
            raise CommandError("Le nom de base PostgreSQL est obligatoire.")

        dump_format = "custom" if requested_format == "auto" else requested_format
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        extension = "dump" if dump_format == "custom" else "sql"
        target = output_dir / f"{db_name}-{timestamp}.{extension}"

        cmd = ["pg_dump"]
        if dump_format == "custom":
            cmd.append("--format=c")
        else:
            cmd.append("--format=p")
        cmd.extend(["--no-owner", "--no-privileges", f"--file={target}"])

        if db_config.get("HOST"):
            cmd.extend(["--host", str(db_config["HOST"])])
        if db_config.get("PORT"):
            cmd.extend(["--port", str(db_config["PORT"])])
        if db_config.get("USER"):
            cmd.extend(["--username", str(db_config["USER"])])
        cmd.append(db_name)

        env = os.environ.copy()
        if db_config.get("PASSWORD"):
            env["PGPASSWORD"] = str(db_config["PASSWORD"])

        try:
            subprocess.run(cmd, check=True, env=env, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise CommandError("pg_dump est introuvable. Installez le client PostgreSQL sur le serveur.") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip()
            raise CommandError(f"Echec de la sauvegarde PostgreSQL: {stderr or 'erreur inconnue'}") from exc

        return target

    def handle(self, *args, **options):
        db_config = settings.DATABASES["default"]
        engine = str(db_config.get("ENGINE", "")).lower()
        output_dir = Path(options["output_dir"] or settings.BACKUP_ROOT)
        output_dir.mkdir(parents=True, exist_ok=True)

        if "sqlite" in engine:
            target = self._backup_sqlite(db_config, output_dir)
        elif "postgresql" in engine:
            target = self._backup_postgresql(db_config, output_dir, options["format"])
        else:
            raise CommandError(f"Moteur non supporte pour la sauvegarde automatique: {db_config.get('ENGINE')}")

        self.stdout.write(self.style.SUCCESS(f"Sauvegarde creee: {target}"))
