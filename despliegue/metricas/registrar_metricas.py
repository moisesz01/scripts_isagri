"""Registro ligero de consumo (CPU, RAM, red y disco) de la VM de Prefect.

Toma una muestra cada N segundos leyendo /proc (solo librería estándar, no
hace falta instalar nada) y escribe dos CSV en la carpeta de salida:

  sistema.csv   -> la VM completa: CPU %, RAM usada/disponible, carga,
                   red (KB/s recibidos/enviados) y disco (KB/s leídos/escritos)
  procesos.csv  -> por componente: servidor de Prefect, PostgreSQL, worker,
                   cada ejecución de un flujo (con su flow_run_id) y el propio
                   medidor. CPU en % de UN núcleo (200 % = los 2 núcleos llenos).

No se conecta a SQL Server ni a Prefect: solo observa.

Uso en la VM (se queda corriendo aunque se cierre la sesión SSH):
  setsid nohup python3 registrar_metricas.py --salida /opt/isagri/metricas \
      --hasta 2026-11-17T04:00:00Z > /opt/isagri/metricas/medidor.log 2>&1 &
"""
import argparse
import csv
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

TICKS = os.sysconf("SC_CLK_TCK")
PAGINA_KB = os.sysconf("SC_PAGE_SIZE") // 1024
DISCO_RE = re.compile(r"^(sd[a-z]+|vd[a-z]+|xvd[a-z]+|nvme\d+n\d+)$")
RED_IGNORAR = ("lo", "docker", "br-", "veth")


def leer(ruta):
    try:
        with open(ruta, "rb") as f:
            return f.read()
    except OSError:
        return None


def cpu_total():
    campos = leer("/proc/stat").split(b"\n", 1)[0].split()[1:]
    valores = list(map(int, campos))
    inactivo = valores[3] + valores[4]  # idle + iowait
    return sum(valores), inactivo


def memoria():
    datos = {}
    for linea in leer("/proc/meminfo").decode().splitlines():
        clave, valor = linea.split(":", 1)
        datos[clave] = int(valor.split()[0])
    total = datos["MemTotal"] / 1024
    disponible = datos["MemAvailable"] / 1024
    return total - disponible, disponible


def red():
    rx = tx = 0
    for linea in leer("/proc/net/dev").decode().splitlines()[2:]:
        nombre, resto = linea.split(":", 1)
        nombre = nombre.strip()
        if nombre.startswith(RED_IGNORAR):
            continue
        campos = resto.split()
        rx += int(campos[0])
        tx += int(campos[8])
    return rx, tx


def disco():
    leido = escrito = 0
    for linea in leer("/proc/diskstats").decode().splitlines():
        campos = linea.split()
        if DISCO_RE.match(campos[2]):
            leido += int(campos[5]) * 512
            escrito += int(campos[9]) * 512
    return leido, escrito


def procesos():
    """pid -> (ppid, ticks_cpu, rss_mb, cmdline)."""
    resultado = {}
    for entrada in os.listdir("/proc"):
        if not entrada.isdigit():
            continue
        stat = leer(f"/proc/{entrada}/stat")
        cmd = leer(f"/proc/{entrada}/cmdline")
        if not stat or cmd is None:
            continue
        # el nombre del proceso va entre paréntesis y puede tener espacios
        resto = stat[stat.rfind(b")") + 2:].split()
        ppid = int(resto[1])
        ticks = int(resto[11]) + int(resto[12])
        rss_mb = int(resto[21]) * PAGINA_KB / 1024
        texto = cmd.replace(b"\0", b" ").decode(errors="replace").strip()
        resultado[int(entrada)] = (ppid, ticks, rss_mb, texto)
    return resultado


def flow_run_id(pid):
    entorno = leer(f"/proc/{pid}/environ") or b""
    for var in entorno.split(b"\0"):
        if var.startswith(b"PREFECT__FLOW_RUN_ID="):
            return var.split(b"=", 1)[1].decode()
    return ""


def clasificar(tabla, propio):
    """Asigna a cada pid un componente; los hijos heredan el del padre."""
    raiz = {}
    for pid, (_, _, _, cmd) in tabla.items():
        if pid == propio:
            raiz[pid] = ("medidor", "")
        elif "prefect.engine" in cmd or "prefect/engine" in cmd:
            raiz[pid] = ("flujo", flow_run_id(pid))
        elif "prefect worker" in cmd:
            raiz[pid] = ("worker", "")
        elif "prefect server" in cmd or "uvicorn" in cmd:
            raiz[pid] = ("prefect-server", "")
        elif cmd.startswith("postgres"):
            raiz[pid] = ("postgres", "")

    def grupo(pid, profundidad=0):
        if pid in raiz:
            return raiz[pid]
        padre = tabla.get(pid, (0,))[0]
        if padre <= 1 or profundidad > 20:
            return None
        return grupo(padre, profundidad + 1)

    return {pid: g for pid in tabla if (g := grupo(pid))}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--salida", default="/opt/isagri/metricas")
    p.add_argument("--intervalo", type=float, default=5)
    p.add_argument("--hasta", help="fecha/hora UTC de fin, ej. 2026-11-17T04:00:00Z")
    args = p.parse_args()

    fin = datetime.fromisoformat(args.hasta.replace("Z", "+00:00")) if args.hasta else None
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    propio = os.getpid()

    f_sis = open(salida / "sistema.csv", "a", newline="")
    f_proc = open(salida / "procesos.csv", "a", newline="")
    w_sis, w_proc = csv.writer(f_sis), csv.writer(f_proc)
    if f_sis.tell() == 0:
        w_sis.writerow(["ts_utc", "cpu_pct", "ram_usada_mb", "ram_disponible_mb", "carga_1m",
                        "red_rx_kbs", "red_tx_kbs", "disco_lee_kbs", "disco_escribe_kbs"])
    if f_proc.tell() == 0:
        w_proc.writerow(["ts_utc", "componente", "flow_run_id", "cpu_pct", "rss_mb", "n_procesos"])

    prev_cpu, prev_red, prev_disco = cpu_total(), red(), disco()
    prev_ticks = {pid: v[1] for pid, v in procesos().items()}
    prev_t = time.monotonic()

    while fin is None or datetime.now(timezone.utc) < fin:
        time.sleep(args.intervalo)
        t = time.monotonic()
        dt = t - prev_t
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        total, inactivo = cpu_total()
        d_total = total - prev_cpu[0]
        cpu_pct = 100 * (1 - (inactivo - prev_cpu[1]) / d_total) if d_total else 0
        usada, disponible = memoria()
        carga = float(leer("/proc/loadavg").split()[0])
        rx, tx = red()
        lee, escribe = disco()
        w_sis.writerow([ts, f"{cpu_pct:.1f}", f"{usada:.0f}", f"{disponible:.0f}", carga,
                        f"{(rx - prev_red[0]) / 1024 / dt:.1f}", f"{(tx - prev_red[1]) / 1024 / dt:.1f}",
                        f"{(lee - prev_disco[0]) / 1024 / dt:.1f}",
                        f"{(escribe - prev_disco[1]) / 1024 / dt:.1f}"])

        tabla = procesos()
        acumulado = {}
        for pid, (comp, run_id) in clasificar(tabla, propio).items():
            _, ticks, rss, _ = tabla[pid]
            delta = ticks - prev_ticks.get(pid, ticks)
            a = acumulado.setdefault((comp, run_id), [0.0, 0.0, 0])
            a[0] += 100 * delta / TICKS / dt
            a[1] += rss
            a[2] += 1
        for (comp, run_id), (cpu, rss, n) in sorted(acumulado.items()):
            w_proc.writerow([ts, comp, run_id, f"{cpu:.1f}", f"{rss:.0f}", n])

        f_sis.flush()
        f_proc.flush()
        prev_cpu, prev_red, prev_disco, prev_t = (total, inactivo), (rx, tx), (lee, escribe), t
        prev_ticks = {pid: v[1] for pid, v in tabla.items()}


if __name__ == "__main__":
    main()
