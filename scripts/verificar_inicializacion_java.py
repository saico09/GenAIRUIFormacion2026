"""Prueba el bootstrap compartido en PG/Java nuevos; elimina solamente sus recursos Docker etiquetados."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--java-image", default="genairuiformacion2026-java-api:latest")
    parser.add_argument("--postgres-image", default="postgres:18.6-alpine")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    name = "genai-bootstrap-" + uuid4().hex[:10]
    label = "genai.bootstrap.test=" + name
    local = (ROOT / ".local" / name).resolve()
    local.mkdir(parents=True)
    data = local / "datos"
    (data / "historias").mkdir(parents=True)
    shutil.copy2(ROOT / "datos/pacientes.json", data / "pacientes.json")
    for patient_id, name_part in ((1, "ana"), (2, "bruno"), (3, "carla")):
        filename = f"paciente-{patient_id}-{name_part}-demo.md"
        seed = subprocess.check_output(["git", "-C", str(ROOT), "show", f"HEAD:datos/historias/{filename}"])
        (data / "historias" / filename).write_bytes(seed)
    env = os.environ.copy()
    env["POSTGRES_PASSWORD"] = secrets.token_urlsafe(32)
    image, pg, java, runner = [name + suffix for suffix in (":test", "-pg", "-java", "-python")]
    volume = name + "-data"
    containers, resources = [], []
    evidence = {"started_at": datetime.now(timezone.utc).isoformat(), "result": "running",
                "isolation": {"name": name, "network": name, "volume": volume,
                              "original_data_mounted": False}, "checks": []}

    def save():
        args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def docker(*command, input=None, check=True):
        result = subprocess.run(["docker", *command], input=input, text=True, encoding="utf-8",
                                errors="replace", capture_output=True, env=env, timeout=240)
        if check and result.returncode:
            # Las salidas de Docker pueden contener variables: no volcarlas como evidencia.
            raise RuntimeError("Docker falló: " + " ".join(command[:3]))
        return result

    def sql_query(statement, params=None):
        script = ("import os,json,psycopg\n"
                  "with psycopg.connect(host=os.environ['POSTGRES_HOST'],dbname=os.environ['POSTGRES_DB'],"
                  "user=os.environ['POSTGRES_USER'],password=os.environ['POSTGRES_PASSWORD']) as c:\n"
                  f" r=c.execute({statement!r}, {params!r})\n"
                  " print(json.dumps(r.fetchall() if r.description else [],default=str))\n")
        return json.loads(docker("exec", "-i", runner, "python", "-", input=script).stdout)

    def state():
        rows = sql_query("SELECT id,name,birth_date,email FROM public.patients ORDER BY id")
        return {"count": len(rows), "ids": [row[0] for row in rows],
                "rows_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
                "sequence": sql_query("SELECT last_value,is_called FROM public.patients_id_seq")[0]}

    def files():
        return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted((data / "historias").glob("*.md"))}

    def cli(*options, success=True):
        result = docker("exec", runner, "python", "inicializar_datos.py", *options, check=False)
        assert (result.returncode == 0) == success, ("CLI exit", result.returncode)
        return json.loads((result.stdout if success else result.stderr).strip().splitlines()[-1])

    def mark(check, **details):
        evidence["checks"].append({"check": check, "passed": True, **details})
        save()
        print(check + ": PASS", flush=True)

    def http(path, method="GET", body=None, expected=200):
        request = Request(base + path, method=method,
                          data=json.dumps(body).encode() if body is not None else None,
                          headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=10) as response:
                status, raw = response.status, response.read()
        except HTTPError as error:
            status, raw = error.code, error.read()
        assert status == expected, (path, status, expected)
        return json.loads(raw) if raw else None

    try:
        save()
        build = docker("build", "--label", label, "-t", image, str(ROOT / "python-api"), check=False)
        args.output.with_suffix(".build.txt").write_text(build.stdout + build.stderr, encoding="utf-8")
        assert build.returncode == 0, "Build Python falló"
        docker("network", "create", "--label", label, name)
        resources.append(("network", name))
        docker("volume", "create", "--label", label, volume)
        resources.append(("volume", volume))
        common = ["--network", name, "--label", label, "-e", "POSTGRES_DB=bootstrap",
                  "-e", "POSTGRES_USER=bootstrap", "-e", "POSTGRES_PASSWORD"]
        docker("run", "-d", "--name", pg, *common, "--mount", f"type=volume,src={volume},dst=/var/lib/postgresql",
               args.postgres_image)
        containers.append(pg)
        for _ in range(90):
            if docker("exec", pg, "pg_isready", "-U", "bootstrap", "-d", "bootstrap", check=False).returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("PostgreSQL aislado no inició")
        docker("run", "-d", "--name", runner, *common, "-e", "POSTGRES_HOST=" + pg,
               "--mount", f"type=bind,src={data},dst=/datos", image,
               "python", "-c", "import time;time.sleep(1800)")
        containers.append(runner)
        docker("run", "-d", "--name", java, *common, "-e", "POSTGRES_HOST=" + pg,
               "--mount", f"type=bind,src={data / 'historias'},dst=/historias",
               "-p", "127.0.0.1::8080", args.java_image)
        containers.append(java)
        port = json.loads(docker("inspect", java).stdout)[0]["NetworkSettings"]["Ports"]["8080/tcp"][0]["HostPort"]
        base = "http://127.0.0.1:" + port
        evidence["isolation"]["java_url"] = base
        evidence["images"] = {container: json.loads(docker("inspect", container).stdout)[0]["Image"]
                              for container in containers}
        for _ in range(120):
            try:
                http("/health")
                break
            except (URLError, TimeoutError, ConnectionError, AssertionError):
                time.sleep(1)
        else:
            raise RuntimeError("Java aislado no inició")
        before = state()
        original_files = files()
        assert before["count"] == 0 and http("/patients") == []
        mark("primer_arranque_tabla_vacia", sequence=before["sequence"])

        target = next((data / "historias").glob("paciente-1-*.md"))
        original = target.read_bytes()
        for reason, changed in (
            ("nombre", original.replace(b"Ana Demo", b"Otra Demo", 1)),
            ("propietario", original.replace(b"patient_id: 1", b"patient_id: 9", 1)),
            ("uuid", original.replace(b"## Registro ", b"## Registro invalido-", 1)),
        ):
            target.write_bytes(changed)
            invalid_files = files()
            failure = cli(success=False)
            assert state() == before and files() == invalid_files
            target.write_bytes(original)
            mark("rechazo_sin_escrituras_" + reason, error_type=failure["error_type"])

        sql_query("""CREATE FUNCTION public.reject_demo() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.id = 2 THEN RAISE EXCEPTION 'test' USING ERRCODE='23514'; END IF; RETURN NEW; END $$""")
        sql_query("CREATE TRIGGER reject_demo BEFORE INSERT ON public.patients FOR EACH ROW EXECUTE FUNCTION public.reject_demo()")
        failure = cli(success=False)
        assert failure["sqlstate"] == "23514" and state() == before and files() == original_files
        sql_query("DROP TRIGGER reject_demo ON public.patients")
        sql_query("DROP FUNCTION public.reject_demo()")
        mark("rollback_filas_y_restart_secuencia", sqlstate=failure["sqlstate"])

        dataset = json.loads((data / "pacientes.json").read_text(encoding="utf-8"))
        for patient in dataset:
            http("/patients", "POST", patient, expected=409)
        assert state()["count"] == 0 and state()["sequence"] == [3, True] and files() == original_files
        mark("post_no_adopta_informes_y_consume_ids", sequence=[3, True])

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: cli(), range(2)))
        assert sorted(result["status"] for result in results) == ["conservados", "inicializados"]
        assert state()["ids"] == [1, 2, 3] and state()["sequence"] == [4, False]
        patients = http("/patients")
        assert sorted(patients, key=lambda row: row["id"]) == [dict(id=i, **item) for i, item in enumerate(dataset, 1)]
        for patient in patients:
            history = http(f"/patients/{patient['id']}/history")
            assert history["entries"] and history["revision"] == original_files[history["filename"]]
        assert files() == original_files
        mark("dos_inicializadores_serializados_y_md_preservados", results=results)

        temporary = {"name": "Prueba Bootstrap", "birth_date": "1995-05-05", "email": "bootstrap@example.com"}
        created = http("/patients", "POST", temporary, expected=201)
        assert created["id"] == 4 and http("/patients/4/history")["entries"] == []
        http("/patients/4", "DELETE", expected=204)
        assert files() == original_files
        mark("siguiente_paciente_api_id4_y_limpieza")

        existing = state()
        result = cli("--data-dir", "/no-existe")
        assert result["status"] == "conservados" and state() == existing and files() == original_files
        mark("repeticion_con_datos_no_lee_ni_toca_demo_o_secuencia", count=existing["count"])

        # Solo la BD efímera de este test: simula una secuencia ya consumida por intentos previos.
        sql_query("DELETE FROM public.patients")
        sql_query("SELECT setval('public.patients_id_seq',20,true)")
        empty = state()
        failure = cli(success=False)
        assert failure["error_type"] == "ValueError" and state() == empty
        mark("no_recrear_pacientes_borrados_con_historial", preserved=True)
        created = http("/patients", "POST", temporary, expected=201)
        assert created["id"] == 21
        http("/patients/21", "DELETE", expected=204)
        assert files() == original_files
        mark("secuencia_avanzada_no_retrocede", next_id=21)
        evidence["final"] = state()
        evidence["markdown_sha256"] = original_files
        evidence["result"] = "passed"
    except Exception as error:
        evidence["result"] = "failed"
        evidence["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        removed = []
        for container in reversed(containers):
            info = json.loads(docker("inspect", container).stdout)[0]
            assert info["Config"]["Labels"].get("genai.bootstrap.test") == name
            docker("rm", "-f", container)
            removed.append(container)
        for kind, resource in reversed(resources):
            info = json.loads(docker(kind, "inspect", resource).stdout)[0]
            assert info["Labels"].get("genai.bootstrap.test") == name
            docker(kind, "rm", resource)
            removed.append(resource)
        docker("image", "rm", image, check=False)
        assert local.parent == (ROOT / ".local").resolve() and local.name == name
        shutil.rmtree(local)
        evidence["cleanup"] = {"removed_owned_resources": removed, "temporary_files_removed": True}
        evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
        save()
    print("Bootstrap compartido: PASS; recursos efímeros eliminados.")


if __name__ == "__main__":
    main()
