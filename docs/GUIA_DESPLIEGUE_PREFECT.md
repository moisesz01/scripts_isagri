# Guía de instalación: Prefect para scripts_isagri

Esta guía explica, paso a paso, cómo montar desde cero la máquina virtual (VM) Ubuntu que ejecuta las sincronizaciones Paradox → SQL Server con **Prefect**, sustituyendo al Programador de Tareas de Windows.

Todo lo que aparece aquí se probó en la VM de pruebas en noviembre de 2026.

---

## Antes de empezar: cómo leer esta guía

### Dónde se ejecuta cada cosa

Cada paso indica **dónde** hay que hacerlo con uno de estos iconos:

| Icono | Dónde | Cómo se abre |
|---|---|---|
| 💻 | **Terminal de tu equipo** (tu Mac o PC de administración) | Mac: app **Terminal**. Windows 10/11: **PowerShell**. |
| 🐧 | **Terminal de la VM** | Desde la terminal de tu equipo, conéctate con `ssh moisesz01@IP-DE-LA-VM` (paso 2). Sabrás que estás dentro porque la línea empieza por `moisesz01@UbuntuServer`. |
| 🌐 | **Navegador** | Chrome, Edge, Safari… |
| 🖱️ | **Consola de la VM** | La ventana de Hyper-V / VirtualBox donde ves la VM directamente. |

### Cómo ejecutar los comandos

- Cada recuadro gris es **un comando**. Cópialo entero, pégalo en la terminal y pulsa **Enter**. Espera a que termine (vuelve a aparecer la línea `moisesz01@...$`) antes de pasar al siguiente.
- **Pegar en la terminal:** Mac → `Cmd + V`. PowerShell → clic derecho o `Ctrl + V`. PuTTY → clic derecho.
- Si un comando pide **contraseña** (por ejemplo `[sudo] password for moisesz01:`), escribe la contraseña del usuario de la VM y pulsa Enter. **No se ve nada mientras escribes**: es normal.
- Las líneas que empiezan por `#` dentro de un recuadro son comentarios: no hace falta copiarlas.
- Debajo de muchos comandos hay un **"Deberías ver"**. Si ves algo distinto, consulta [Problemas frecuentes](#problemas-frecuentes) antes de seguir.

### Datos que se usan en esta guía

Cámbialos por los tuyos donde aparezcan:

| Dato | Valor en esta guía |
|---|---|
| IP de la VM | `192.168.0.110` |
| Usuario de la VM | `moisesz01` |
| Carpeta de instalación en la VM | `/opt/isagri` |

### Cómo editar un archivo en la VM (nano)

Varios pasos piden editar un archivo con `nano`, un editor de texto que funciona dentro de la terminal:

1. Muévete con las **flechas** del teclado (el ratón no funciona) y escribe normalmente.
2. Para **guardar**: `Ctrl + O` y después **Enter**.
3. Para **salir**: `Ctrl + X`.

---

## Resumen: qué se va a montar

```
┌──────────────────────────── VM Ubuntu ────────────────────────────┐
│                                                                   │
│  Docker                                                           │
│  ├─ prefect-postgres   base de datos de Prefect (historial)       │
│  └─ prefect-server     dashboard web, puerto 4200  ───────────────┼──► 🌐 http://IP:4200
│                                                                   │
│  prefect-worker (servicio)                                        │
│  └─ ejecuta los scripts a su hora ──► Azure Blob (tablas Paradox) │
│                                   └─► Azure SQL (SQL Server)      │
│                                   └─► Teams (avisos si algo falla)│
└───────────────────────────────────────────────────────────────────┘
```

Los 8 procesos que se programan (uno por cada `.bat` del Programador de Tareas):

| Proceso en Prefect | Qué hace | Antes era |
|---|---|---|
| `paradox-actirep` | Actirep → `actirep_finanzas` | `TablaActirep.bat` |
| `paradox-docen` | DOCEN, DELRG, Docec, ADHES, codiv → `*_finanzas` | `TablaDocen.bat` |
| `paradox-ecri` | Ecri → `ecri_finanzas` | `TablaEcri.bat` |
| `paradox-mvts` | mvts → `mvts_finanzas` (últimos 548 días) | `TablaMvts.bat` |
| `paradox-balan-balme` | BALAN, BALME → `balan_finanzas`, `balme_finanzas` | `TablasBalanBalme.bat` |
| `compras-detalle-pedidos` | `docli_t` (pedidos) → `detalle_pedido_compras` | `detalle_pedidos_compras.bat` |
| `compras-detalle-albaranes` | `docli_t` (albaranes) → `detalle_albaran_compras`, y enlaza pedidos | `detalle_albaranes_compras.bat` |
| `compras-asociacion-factura-albaran` | Enlaza las facturas de los últimos 90 días con sus albaranes | `asociacion_factura_albaran.bat` |

**Tiempo estimado:** 1–2 horas.

---

## Paso 1. Crear la VM y fijarle la IP

### 1.1 Crear la VM

🖱️ En Hyper-V (o el hipervisor que uséis), crea una VM con:

- **Ubuntu Server 26.04 LTS** (también vale 24.04 LTS).
- **2 CPU, 4 GB de RAM y 30 GB de disco** (con 3 GB funciona, pero 4 es más holgado).
- En **Hyper-V de Windows Server 2012 (no R2)**: créala como **Generación 1** y con un adaptador de red **normal**, no "heredado" (*legacy*).
- En **Hyper-V**, deja activado *Integration Services → Time synchronization* (sincroniza la hora de la VM).

Durante la instalación de Ubuntu:
- Crea el usuario `moisesz01` (o el que prefieras: si es otro, cámbialo en toda la guía).
- Marca **"Install OpenSSH server"**.

### 1.2 Fijar la IP (importante)

Si la VM recibe la IP por DHCP, puede cambiar sola (en la VM de pruebas pasó de `.17` a `.110`). Cuando cambia, el dashboard deja de funcionar hasta que se actualiza la configuración. Hay dos formas de fijarla:

**Opción A (recomendada): reserva en el router.** Pide a quien administre la red una "reserva DHCP" para la MAC de la VM. Para ver la MAC y la IP actual:

🖱️ o 🐧
```bash
ip -4 addr
```

```bash
ip link
```

Deberías ver la IP en una línea como `inet 192.168.0.110/24 ... enp0s3` y la MAC en una línea como `link/ether 20:0b:74:6e:40:db`.

**Opción B: IP fija en la propia VM** (con netplan).

🐧 Crea el archivo de configuración:
```bash
sudo nano /etc/netplan/60-ip-fija.yaml
```

Escribe esto dentro, cambiando `enp0s3` por el nombre de tu interfaz (lo ves con `ip -4 addr`), la IP, y la puerta de enlace (`via`) de tu red:

```yaml
network:
  version: 2
  ethernets:
    enp0s3:
      dhcp4: false
      addresses: [192.168.0.110/24]
      routes:
        - to: default
          via: 192.168.0.1
      nameservers:
        addresses: [192.168.0.1, 1.1.1.1]
```

Guarda (`Ctrl + O`, Enter) y sal (`Ctrl + X`). Después:

```bash
sudo chmod 600 /etc/netplan/60-ip-fija.yaml
```

```bash
sudo netplan apply
```

> Si estabas conectado por SSH y cambias la IP, se cortará la conexión: vuelve a conectarte con la IP nueva.

---

## Paso 2. Conectarte a la VM por SSH desde tu equipo

Se usa una **clave SSH** en lugar de la contraseña: es más seguro y no tendrás que escribirla cada vez.

### 2.1 Crear tu clave (solo la primera vez)

💻 En la terminal de tu equipo:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""
```

> En Windows/PowerShell usa: `ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\id_ed25519 -N '""'`
>
> Si dice que el archivo ya existe, ya tienes una clave: responde `n` y sigue.

### 2.2 Copiar tu clave a la VM

💻 **Mac o Linux:**

```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub moisesz01@192.168.0.110
```

💻 **Windows (PowerShell)**, que no tiene `ssh-copy-id`:

```powershell
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh moisesz01@192.168.0.110 "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

Te pedirá la contraseña del usuario de la VM **una vez**. La primera vez también preguntará `Are you sure you want to continue connecting (yes/no)?`: escribe `yes`.

Deberías ver (en Mac): `Number of key(s) added: 1`.

### 2.3 Comprobar

💻
```bash
ssh moisesz01@192.168.0.110
```

**Deberías entrar sin que te pida contraseña** y ver una línea como `moisesz01@UbuntuServer:~$`. A partir de aquí, todos los pasos con 🐧 se ejecutan en esta sesión. Para salir de la VM: `exit`.

---

## Paso 3. Preparar Ubuntu

🐧 Todo este paso se ejecuta **dentro de la VM**. Algunos comandos piden la contraseña de `sudo` (la del usuario de la VM).

### 3.1 Actualizar el sistema

Descarga e instala las actualizaciones de Ubuntu (puede tardar varios minutos):

```bash
sudo apt-get update
```

```bash
sudo apt-get upgrade -y
```

Si aparece una pantalla morada preguntando qué servicios reiniciar, pulsa **Enter** para aceptar.

### 3.2 Instalar herramientas básicas

Python, git y librerías que necesitan los conectores de SQL Server:

```bash
sudo apt-get install -y ca-certificates curl gnupg git rsync python3-venv python3-dev build-essential unixodbc unixodbc-dev
```

### 3.3 Instalar Docker

Docker ejecuta el servidor de Prefect y su base de datos. Estos comandos añaden el repositorio oficial de Docker e instalan Docker y Docker Compose. Ejecútalos **de uno en uno**:

```bash
sudo install -m 0755 -d /etc/apt/keyrings
```

```bash
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
```

```bash
sudo chmod a+r /etc/apt/keyrings/docker.asc
```

```bash
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list
```

```bash
sudo apt-get update
```

```bash
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

```bash
sudo systemctl enable --now docker
```

Comprueba que está instalado:

```bash
sudo docker --version
```

```bash
sudo docker compose version
```

Deberías ver algo como `Docker version 29.9.3` y `Docker Compose version v5.7.1` (o versiones más nuevas).

### 3.4 Instalar el driver de SQL Server (ODBC 18)

Es lo que permite a Python conectarse a Azure SQL. Ejecuta de uno en uno:

```bash
curl -fsSL -o /tmp/packages-microsoft-prod.deb https://packages.microsoft.com/config/ubuntu/$(. /etc/os-release && echo $VERSION_ID)/packages-microsoft-prod.deb
```

```bash
sudo dpkg -i /tmp/packages-microsoft-prod.deb
```

```bash
sudo apt-get update
```

```bash
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18
```

Comprueba:

```bash
odbcinst -q -d
```

Deberías ver: `[ODBC Driver 18 for SQL Server]`

---

## Paso 4. Copiar el proyecto a la VM

### 4.1 Crear la carpeta de instalación

🐧
```bash
sudo mkdir -p /opt/isagri
```

```bash
sudo chown moisesz01:moisesz01 /opt/isagri
```

(Cambia `moisesz01:moisesz01` si tu usuario es otro.)

### 4.2 Descargar el código

Elige **una** de las dos opciones.

**Opción A (recomendada): descargarlo de GitHub** directamente en la VM.

Si el repositorio es **público**:

🐧
```bash
git clone https://github.com/moisesz01/scripts_isagri.git /opt/isagri/scripts_isagri
```

Si el repositorio es **privado**, hay que dar a la VM permiso de solo lectura con una *deploy key*:

1. 🐧 Crea una clave para GitHub:
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/github_isagri -N ""
   ```
2. 🐧 Muestra la clave pública y cópiala (toda la línea, empieza por `ssh-ed25519`):
   ```bash
   cat ~/.ssh/github_isagri.pub
   ```
3. 🌐 En GitHub: repositorio `scripts_isagri` → **Settings** → **Deploy keys** → **Add deploy key**. Pega la clave, ponle de título "VM Prefect" y **no** marques "Allow write access". Guarda.
4. 🐧 Descarga el código:
   ```bash
   GIT_SSH_COMMAND="ssh -i ~/.ssh/github_isagri -o StrictHostKeyChecking=accept-new" git clone git@github.com:moisesz01/scripts_isagri.git /opt/isagri/scripts_isagri
   ```

**Opción B: copiarlo desde tu equipo.**

💻 Desde la carpeta del proyecto en tu Mac:

```bash
rsync -a --exclude .git --exclude '__pycache__' --exclude .env --exclude tmp --exclude logs ./ moisesz01@192.168.0.110:/opt/isagri/scripts_isagri/
```

> En Windows, sin `rsync`: `scp -r C:\ruta\scripts_isagri moisesz01@192.168.0.110:/opt/isagri/` (y después borra en la VM la carpeta `.env` si la copiaste por error de otro sitio).

Comprueba en la VM:

🐧
```bash
ls /opt/isagri/scripts_isagri
```

Deberías ver, entre otros: `Compras  comun  despliegue  docs  orquestacion  prefect.yaml  requirements.txt  TablaActirep ...`

### 4.3 Crear el archivo de credenciales del proyecto (`.env`)

El archivo `.env` guarda las credenciales de SQL Server y los enlaces de descarga de las tablas Paradox. Es **el mismo** que el de Windows, con **un cambio**: en Linux el driver es el 18.

**Si ya tienes el `.env` de Windows**, cópialo a la VM:

💻 Desde la carpeta donde tengas el `.env`:

```bash
scp .env moisesz01@192.168.0.110:/opt/isagri/scripts_isagri/.env
```

**Si no lo tienes**, créalo a partir de la plantilla:

🐧
```bash
cp /opt/isagri/scripts_isagri/.env_example /opt/isagri/scripts_isagri/.env
```

Después, en cualquiera de los dos casos, ábrelo para revisarlo:

🐧
```bash
nano /opt/isagri/scripts_isagri/.env
```

Comprueba o rellena:
- `Server`, `Database`, `UsernameDB`, `Password`: datos de Azure SQL.
- Las 10 líneas `PARADOX_URL_...`: enlaces de descarga (con token SAS) de cada tabla Paradox.
- **El driver**: debe haber una línea exactamente así (añádela si no está, o cambia el 17 por el 18):
  ```
  SqlDriver = 'ODBC Driver 18 for SQL Server'
  ```

Guarda (`Ctrl + O`, Enter) y sal (`Ctrl + X`). Después protege el archivo para que solo tu usuario pueda leerlo:

```bash
chmod 600 /opt/isagri/scripts_isagri/.env
```

---

## Paso 5. Poner en marcha el servidor de Prefect (dashboard)

### 5.1 Preparar la carpeta del servidor

🐧 Copia el `docker-compose.yml` y la plantilla de configuración, que vienen en el proyecto:

```bash
mkdir -p /opt/isagri/prefect-server
```

```bash
cp /opt/isagri/scripts_isagri/despliegue/docker-compose.yml /opt/isagri/scripts_isagri/despliegue/.env.example /opt/isagri/prefect-server/
```

```bash
cd /opt/isagri/prefect-server
```

### 5.2 Crear la configuración del servidor con contraseñas seguras

Este comando crea el archivo `.env` del servidor a partir de la plantilla y genera **dos contraseñas aleatorias**: la de la base de datos y la del dashboard:

```bash
sed -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 24)/" -e "s/^PREFECT_AUTH_STRING=.*/PREFECT_AUTH_STRING=admin:$(openssl rand -hex 12)/" .env.example > .env
```

```bash
chmod 600 .env
```

Ahora **pon la IP de la VM**. Ábrelo:

```bash
nano .env
```

Cambia la línea `SERVER_IP=...` por la IP real de la VM, por ejemplo `SERVER_IP=192.168.0.110`. **No toques** el resto. Guarda (`Ctrl + O`, Enter) y sal (`Ctrl + X`).

> ⚠️ `SERVER_IP` **debe coincidir siempre con la IP real de la VM**. Si no coincide, el login del dashboard se queda colgado en "Logging in..." y los enlaces de los avisos de Teams no funcionan.

### 5.3 Arrancar el servidor

Descarga las imágenes y arranca los dos contenedores (la primera vez tarda unos minutos):

```bash
sudo docker compose up -d
```

Espera **un minuto** y comprueba el estado:

```bash
sudo docker compose ps
```

Deberías ver los dos en `(healthy)`:

```
NAME               STATUS
prefect-postgres   Up 1 minute (healthy)
prefect-server     Up 1 minute (healthy)
```

Si sale `(health: starting)`, espera otro minuto y repite el comando.

### 5.4 Entrar al dashboard

🐧 Muestra la contraseña del dashboard:

```bash
grep ^PREFECT_AUTH_STRING /opt/isagri/prefect-server/.env | cut -d= -f2
```

Verás algo como `admin:3f9c1a...`. **Cópiala entera, incluido `admin:`**.

🌐 Abre **http://192.168.0.110:4200**. Aparece una pantalla de *Login* con un solo campo: pega la línea completa y pulsa **Log in**. Deberías ver el dashboard de Prefect (vacío de momento).

> El dashboard está en inglés: no tiene opción de idioma. Puedes usar la traducción automática del navegador (clic derecho → *Traducir al español*).

---

## Paso 6. Entorno de Python

### 6.1 Crear el entorno virtual e instalar las librerías

Un **entorno virtual** (venv) es una carpeta con su propia copia de Python y de las librerías que necesitan los scripts (Prefect, pypxlib, pyodbc…), separada del Python del sistema.

🐧 Crea el entorno en `/opt/isagri/venv`:

```bash
python3 -m venv /opt/isagri/venv
```

Actualiza su instalador de paquetes (`pip`):

```bash
/opt/isagri/venv/bin/pip install --upgrade pip
```

Instala las librerías que indica `requirements.txt` (tarda 1–2 minutos):

```bash
/opt/isagri/venv/bin/pip install -r /opt/isagri/scripts_isagri/requirements.txt
```

### 6.2 Comprobar que funciona

```bash
/opt/isagri/venv/bin/python -c "import prefect, pyodbc, pypxlib; print(prefect.__version__, pyodbc.drivers()); print('Todo OK')"
```

Deberías ver:

```
3.9.2 ['ODBC Driver 18 for SQL Server']
Todo OK
```

> No hace falta "activar" el entorno: en esta guía siempre se usa con la ruta completa (`/opt/isagri/venv/bin/...`).

---

## Paso 7. Conectar Prefect (línea de comandos) al servidor

Los comandos `prefect ...` de la VM necesitan saber dónde está el servidor y su contraseña. Se guardan en un "perfil" llamado `isagri`.

🐧 Guarda la contraseña del dashboard en una variable temporal (no se muestra en pantalla):

```bash
AUTH=$(grep ^PREFECT_AUTH_STRING /opt/isagri/prefect-server/.env | cut -d= -f2)
```

Crea el perfil y actívalo:

```bash
/opt/isagri/venv/bin/prefect profile create isagri
```

```bash
/opt/isagri/venv/bin/prefect profile use isagri
```

Guarda en el perfil la dirección del servidor y la contraseña (`> /dev/null` evita que la contraseña aparezca en pantalla):

```bash
/opt/isagri/venv/bin/prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api "PREFECT_API_AUTH_STRING=$AUTH" > /dev/null
```

Comprueba la conexión:

```bash
/opt/isagri/venv/bin/prefect config view --hide-sources | grep -v AUTH_STRING
```

Deberías ver `you are connected to: http://127.0.0.1:4200` y `PREFECT_API_URL='http://127.0.0.1:4200/api'`.

> Si cierras la sesión SSH entre comandos, la variable `AUTH` se pierde: vuelve a ejecutar el primer comando de este paso.

---

## Paso 8. Poner en marcha el worker

El **worker** es el proceso que, a la hora programada, ejecuta los scripts. Se instala como servicio para que arranque solo al encender la VM.

### 8.1 Crear la cola de trabajo

🐧
```bash
/opt/isagri/venv/bin/prefect work-pool create isagri-pool --type process
```

Deberías ver: `Created work pool 'isagri-pool'!`

### 8.2 Darle al worker la dirección y la contraseña del servidor

```bash
AUTH=$(grep ^PREFECT_AUTH_STRING /opt/isagri/prefect-server/.env | cut -d= -f2)
```

```bash
printf "PREFECT_API_URL=http://127.0.0.1:4200/api\nPREFECT_API_AUTH_STRING=%s\n" "$AUTH" > /opt/isagri/worker.env
```

```bash
chmod 600 /opt/isagri/worker.env
```

### 8.3 Instalar el servicio y arrancarlo

> Si tu usuario **no** es `moisesz01`, antes edita el archivo y cambia `User=` y `Group=`: `nano /opt/isagri/scripts_isagri/despliegue/systemd/prefect-worker.service`

```bash
sudo cp /opt/isagri/scripts_isagri/despliegue/systemd/prefect-worker.service /etc/systemd/system/
```

```bash
sudo systemctl daemon-reload
```

```bash
sudo systemctl enable --now prefect-worker
```

Comprueba que está funcionando:

```bash
systemctl is-active prefect-worker
```

Deberías ver: `active`

```bash
sudo journalctl -u prefect-worker -n 5 --no-pager
```

Deberías ver, al final: `Worker 'worker-isagri' started!`

🌐 En el dashboard, en **Work Pools** → `isagri-pool`, debe aparecer el worker `worker-isagri` en verde (*Online*).

---

## Paso 9. Registrar los 8 procesos

Este comando lee `prefect.yaml` y da de alta los 8 procesos en el servidor (en Prefect se llaman *deployments*):

🐧
```bash
cd /opt/isagri/scripts_isagri
```

```bash
/opt/isagri/venv/bin/prefect --no-prompt deploy --all
```

Comprueba:

```bash
/opt/isagri/venv/bin/prefect deployment ls
```

Deberías ver los 8:

```
compras-asociacion-factura-albaran/asociacion-factura-albaran
compras-detalle-albaranes/detalle-albaranes
compras-detalle-pedidos/detalle-pedidos
paradox-actirep/actirep
paradox-balan-balme/balan-balme
paradox-docen/docen
paradox-ecri/ecri
paradox-mvts/mvts
```

🌐 También aparecen en el dashboard, en **Deployments**.

---

## Paso 10. Crear los horarios iniciales

Los horarios se gestionan **desde el dashboard**, pero en una instalación nueva hay que crear unos iniciales. Este script los crea **una sola vez** (si un proceso ya tiene horario, no lo toca):

🐧
```bash
/opt/isagri/venv/bin/python /opt/isagri/scripts_isagri/despliegue/crear_horarios_iniciales.py
```

Deberías ver 8 líneas como `paradox-actirep/actirep: horario creado (0 2 * * *, Europe/Madrid)`.

Horarios iniciales (hora de Madrid, todos los días):

| Proceso | Hora |
|---|---|
| `paradox-actirep` | 02:00 |
| `paradox-docen` | 02:20 |
| `paradox-ecri` | 02:40 |
| `paradox-mvts` | 03:00 |
| `paradox-balan-balme` | 03:20 |
| `compras-detalle-pedidos` | 04:00 |
| `compras-detalle-albaranes` | 04:20 |
| `compras-asociacion-factura-albaran` | 04:40 |

Para cambiarlos, mira [Cambiar la hora de un proceso](#cambiar-la-hora-de-un-proceso).

---

## Paso 11. Configurar los avisos a Microsoft Teams

Cuando un proceso falla, o no arranca a su hora, Prefect publica un mensaje en un canal de Teams.

### 11.1 Crear el webhook en Teams

1. Abre Teams y ve al **canal** donde quieres recibir los avisos.
2. Pulsa **⋯** (junto al nombre del canal) → **Workflows**.
3. Elige la plantilla **"Send webhook alerts to a channel"** (en español: *"Publicar en un canal cuando se reciba una solicitud de webhook"*).
4. Sigue el asistente y, al final, **copia la URL** que te da (es muy larga y empieza por `https://`).

> Esa URL funciona como una contraseña: quien la tenga puede publicar en el canal. No la compartas.

### 11.2 Darla de alta en Prefect

🐧 Este comando espera a que pegues la URL. **Pégala y pulsa Enter** (no se verá nada al pegar: es intencionado):

```bash
read -rs TEAMS_WEBHOOK_URL && export TEAMS_WEBHOOK_URL
```

Ahora crea la configuración de avisos y envía un mensaje de prueba:

```bash
/opt/isagri/venv/bin/python /opt/isagri/scripts_isagri/despliegue/configurar_notificaciones.py --prueba
```

Deberías ver:

```
Bloque guardado: teams-isagri
Automatización creada: isagri: ejecución fallida
Automatización creada: isagri: ejecución sin arrancar
Mensaje de prueba enviado
```

Borra la URL de la memoria de la sesión:

```bash
unset TEAMS_WEBHOOK_URL
```

**Comprueba en Teams:** en el canal debe aparecer *"✅ Prueba: los avisos de Prefect (scripts_isagri) llegan a este canal."*

Qué avisos recibirás a partir de ahora:

| Aviso | Cuándo |
|---|---|
| ❌ Ejecución fallida | Un proceso termina con error (*Failed* o *Crashed*). Incluye el error y un enlace a los logs. |
| ⚠️ Ejecución sin arrancar | Un proceso no arrancó a su hora (*Late*). Casi siempre significa que el worker está parado. |

---

## Paso 12. Prueba completa

Lanza a mano cada proceso una vez para comprobar que conecta con Paradox y con SQL Server.

🌐 En el dashboard:
1. **Deployments** → clic en `actirep`.
2. Arriba a la derecha, **Run** → **Quick run**.
3. Ve a **Runs**: la ejecución pasa por *Pending* → *Running* → **Completed** (✓ verde). `actirep` tarda unos 30 segundos.
4. Repite con los otros 7.

> Las ejecuciones manuales escriben en SQL Server igual que las programadas (solo las diferencias con Paradox).

Si alguna termina en **Failed** (rojo), haz clic en ella y mira la pestaña **Logs**: el error aparece en rojo. Te llegará también el aviso a Teams.

---

## Paso 13. Desactivar el Programador de Tareas de Windows

Hazlo **solo cuando** Prefect haya completado al menos una noche con los 8 procesos en **Completed**.

🖱️ En el Windows Server:
1. Abre el **Programador de tareas**.
2. **Deshabilita** (clic derecho → *Deshabilitar*; no las borres) las tareas que lanzan los `.bat`: `TablaActirep`, `TablaDocen`, `TablaEcri`, `TablaMvts`, `TablasBalanBalme`, `detalle_pedidos_compras`, `detalle_albaranes_compras` y `asociacion_factura_albaran`.

> ⚠️ **No dejes los dos sistemas activos a la vez**: escribirían en las mismas tablas de SQL Server.
>
> **Para volver atrás:** en el dashboard, pausa los 8 procesos (ver [Pausar un proceso](#pausar-o-reanudar-un-proceso)) y vuelve a habilitar las tareas de Windows.

---

## Paso 14. Comprobar que todo arranca solo tras un reinicio

🐧
```bash
sudo reboot
```

Se cortará la conexión SSH. Espera **2 minutos** y vuelve a conectarte:

💻
```bash
ssh moisesz01@192.168.0.110
```

🐧 Comprueba:

```bash
sudo docker compose -f /opt/isagri/prefect-server/docker-compose.yml ps
```

```bash
systemctl is-active prefect-worker
```

Deberías ver los dos contenedores en `(healthy)` y el worker en `active`, sin haber arrancado nada a mano. 🎉 **La instalación está terminada.**

---

# Uso diario

Todo esto se hace desde el dashboard 🌐 **http://192.168.0.110:4200**.

### Ver qué se ha ejecutado y si hubo errores

**Runs** muestra todas las ejecuciones. Cada una se llama `<proceso>-<fecha>`, por ejemplo `paradox-mvts-2026-11-17`.

| Estado | Significado |
|---|---|
| ✓ **Completed** (verde) | Terminó bien |
| ✗ **Failed** (rojo) | Terminó con error. Clic en ella → pestaña **Logs** |
| **Crashed** | El proceso se cayó (por ejemplo, se reinició la VM durante la ejecución) |
| **Scheduled** | Programada, pendiente |
| **Late** | Debía haber empezado y no lo hizo: revisa el worker ([Problemas frecuentes](#problemas-frecuentes)) |

En los procesos `paradox-*`, la pestaña **Artifacts** de cada ejecución muestra una tabla con las filas actualizadas, insertadas y borradas por tabla.

### Cambiar la hora de un proceso

1. **Deployments** → clic en el proceso (por ejemplo, `mvts`).
2. En el panel **Schedules** (a la derecha), pulsa **⋮** junto al horario → **Edit**.
3. Elige **Cron** y escribe la hora con el formato `minuto hora * * *`:

   | Quieres | Escribe |
   |---|---|
   | 05:30 todos los días | `30 5 * * *` |
   | 06:00 de lunes a viernes | `0 6 * * 1-5` |
   | Cada 4 horas | `0 */4 * * *` |
   | 07:00 y 19:00 | `0 7,19 * * *` |

4. Comprueba que la zona horaria sea **Europe/Madrid** y pulsa **Save**.

> Las próximas ejecuciones aparecerán con un nombre aleatorio en *Next Run* hasta que el proceso se ejecute una vez; después reciben su nombre con fecha.
>
> Ten en cuenta que los 3 procesos de Compras dependen uno del otro (`detalle-albaranes` usa lo que deja `detalle-pedidos`, y `asociacion-factura-albaran` lo que deja `detalle-albaranes`): mantenlos en ese orden.

### Pausar o reanudar un proceso

**Deployments** → clic en el proceso → en **Schedules**, el **interruptor** junto al horario.

### Lanzar un proceso a mano

**Deployments** → clic en el proceso → **Run** → **Quick run**. Útil para repetir uno que falló.

### Desactivar los avisos de Teams temporalmente

**Automations** → interruptor de `isagri: ejecución fallida` y/o `isagri: ejecución sin arrancar`.

---

# Mantenimiento

### Ver la contraseña del dashboard

🐧
```bash
grep ^PREFECT_AUTH_STRING /opt/isagri/prefect-server/.env | cut -d= -f2
```

### Cambiar la contraseña del dashboard

🐧 Elige la nueva contraseña. Usa solo letras y números, y cambia `MiNuevaClave2026` por la tuya:

```bash
NUEVA='admin:MiNuevaClave2026'
```

Guárdala en el servidor y reinícialo:

```bash
sed -i "s|^PREFECT_AUTH_STRING=.*|PREFECT_AUTH_STRING=$NUEVA|" /opt/isagri/prefect-server/.env
```

```bash
cd /opt/isagri/prefect-server && sudo docker compose up -d
```

Actualiza el worker y la línea de comandos (si no, dejarán de funcionar):

```bash
sed -i "s|^PREFECT_API_AUTH_STRING=.*|PREFECT_API_AUTH_STRING=$NUEVA|" /opt/isagri/worker.env
```

```bash
/opt/isagri/venv/bin/prefect config set "PREFECT_API_AUTH_STRING=$NUEVA" > /dev/null
```

```bash
sudo systemctl restart prefect-worker
```

### Si cambia la IP de la VM

🐧 Pon la IP nueva (cambia `192.168.0.120` por la real):

```bash
sed -i "s|^SERVER_IP=.*|SERVER_IP=192.168.0.120|" /opt/isagri/prefect-server/.env
```

```bash
cd /opt/isagri/prefect-server && sudo docker compose up -d
```

Espera un minuto y entra con la IP nueva. Para que no vuelva a pasar, fija la IP ([Paso 1.2](#12-fijar-la-ip-importante)).

### Actualizar el código

🐧 Si usaste `git clone` (Opción A del paso 4):

```bash
cd /opt/isagri/scripts_isagri && git pull
```

(Con *deploy key*: `GIT_SSH_COMMAND="ssh -i ~/.ssh/github_isagri" git pull`.) Si usaste la Opción B, repite el `rsync` del paso 4.2.

Después, **solo si cambió** `requirements.txt`:

```bash
/opt/isagri/venv/bin/pip install -r /opt/isagri/scripts_isagri/requirements.txt
```

Y **solo si cambió** `prefect.yaml` (procesos nuevos o renombrados):

```bash
cd /opt/isagri/scripts_isagri && /opt/isagri/venv/bin/prefect --no-prompt deploy --all
```

> Los horarios no se pierden al volver a desplegar: se conservan los del dashboard.
>
> Los cambios en los scripts Python se aplican en la siguiente ejecución, sin reiniciar nada.

### Actualizar la versión de Prefect

La versión debe ser **la misma** en el servidor y en el entorno de Python. Cambia el número en los dos archivos:
- `PREFECT_VERSION=` en `/opt/isagri/prefect-server/.env`
- `prefect==` en `/opt/isagri/scripts_isagri/requirements.txt`

Después:

```bash
cd /opt/isagri/prefect-server && sudo docker compose pull && sudo docker compose up -d
```

```bash
/opt/isagri/venv/bin/pip install -r /opt/isagri/scripts_isagri/requirements.txt
```

```bash
sudo systemctl restart prefect-worker
```

### Copia de seguridad del historial de Prefect

🐧 Guarda en tu carpeta personal de la VM un archivo con todo el historial y la configuración:

```bash
sudo docker exec prefect-postgres pg_dump -U prefect prefect | gzip > ~/prefect_$(date +%F).sql.gz
```

### Cambiar el canal de Teams de los avisos

Crea un webhook en el canal nuevo ([Paso 11.1](#111-crear-el-webhook-en-teams)) y repite el [Paso 11.2](#112-darla-de-alta-en-prefect) con la nueva URL.

### Ver los logs técnicos

| Qué | Comando 🐧 |
|---|---|
| Worker (en directo; salir con `Ctrl + C`) | `sudo journalctl -u prefect-worker -f` |
| Servidor (en directo; salir con `Ctrl + C`) | `cd /opt/isagri/prefect-server && sudo docker compose logs -f prefect-server` |
| Reiniciar el worker | `sudo systemctl restart prefect-worker` |
| Reiniciar el servidor | `cd /opt/isagri/prefect-server && sudo docker compose restart` |

---

# Problemas frecuentes

| Qué ves | Qué pasa y cómo se arregla |
|---|---|
| El login del dashboard se queda en **"Logging in..."** | `SERVER_IP` no coincide con la IP real de la VM. Ver [Si cambia la IP de la VM](#si-cambia-la-ip-de-la-vm). |
| El navegador no carga `http://IP:4200` | 🐧 `sudo docker compose -f /opt/isagri/prefect-server/docker-compose.yml ps`: si no están `healthy`, `cd /opt/isagri/prefect-server && sudo docker compose up -d`. Comprueba también que usas la IP correcta. |
| La contraseña del dashboard no funciona | Pega la línea **completa**, incluido `admin:`. Para verla: [Ver la contraseña](#ver-la-contraseña-del-dashboard). Si el navegador recuerda una antigua, prueba en una ventana privada. |
| Los procesos se quedan en **Late** o **Pending** | El worker está parado. 🐧 `systemctl status prefect-worker` y `sudo systemctl restart prefect-worker`. |
| `401 Unauthorized` en el worker o en los comandos `prefect` | La contraseña de `worker.env` o del perfil no coincide con la del servidor. Repite los pasos de [Cambiar la contraseña](#cambiar-la-contraseña-del-dashboard) con la contraseña actual. |
| Error `Can't open lib 'ODBC Driver 17 for SQL Server'` | En la VM está el driver 18: en el `.env` del proyecto pon `SqlDriver = 'ODBC Driver 18 for SQL Server'` ([Paso 4.3](#43-crear-el-archivo-de-credenciales-del-proyecto-env)). |
| Error de conexión a Azure SQL (timeout, login failed) | Revisa usuario y contraseña en el `.env`. Si es un timeout, en el firewall de Azure SQL hay que permitir la **IP pública** de salida de la red de la VM. |
| `Falta la variable PARADOX_URL_...` | Falta esa línea en el `.env` del proyecto, o el token SAS ha caducado: genera uno nuevo en Azure Portal. |
| `leer-paradox` falla con *"no tiene filas"* | La tabla Paradox descargada está vacía. Es una protección intencionada: así no se vacía la tabla de SQL Server. Revisa el archivo en Azure Blob. |
| Horas raras justo después de encender la VM | El reloj se sincroniza al minuto de arrancar. Comprueba con 🐧 `timedatectl` que diga `System clock synchronized: yes`. En Hyper-V, activa *Time synchronization* (paso 1.1). |
| `ssh` pide contraseña | La clave no está instalada: repite el [Paso 2.2](#22-copiar-tu-clave-a-la-vm). |
| `ssh: connect to host ... Operation timed out` | La VM está apagada o ha cambiado de IP. Míralo en la consola de la VM 🖱️ con `ip -4 addr`. |

---

# Anexo A. Archivos de la instalación

| Dónde (en la VM) | Qué es |
|---|---|
| `/opt/isagri/scripts_isagri/` | El código del proyecto |
| `/opt/isagri/scripts_isagri/.env` | Credenciales de SQL Server y enlaces de Paradox (**secreto**) |
| `/opt/isagri/prefect-server/docker-compose.yml` | Definición del servidor de Prefect y su base de datos |
| `/opt/isagri/prefect-server/.env` | IP, contraseñas y versión del servidor (**secreto**) |
| `/opt/isagri/venv/` | Entorno de Python |
| `/opt/isagri/worker.env` | Dirección y contraseña del servidor para el worker (**secreto**) |
| `/etc/systemd/system/prefect-worker.service` | Servicio del worker |

Archivos del repositorio relacionados con Prefect:

| Archivo | Qué es |
|---|---|
| `orquestacion/flujos.py` | Los 8 procesos de Prefect |
| `prefect.yaml` | Registro de los 8 procesos (sin horarios: se gestionan en el dashboard) |
| `requirements.txt` | Librerías de Python y versiones |
| `despliegue/docker-compose.yml`, `despliegue/.env.example` | Servidor de Prefect + PostgreSQL |
| `despliegue/systemd/prefect-worker.service` | Servicio del worker |
| `despliegue/crear_horarios_iniciales.py` | Horarios iniciales (paso 10) |
| `despliegue/configurar_notificaciones.py` | Avisos a Teams (paso 11) |

Versiones probadas: Ubuntu 26.04.1 LTS, Python 3.14, Docker 29.9 / Compose v5.7, Prefect 3.9.2, PostgreSQL 16, ODBC Driver 18, pyodbc 5.5.0, pypxlib 2.5.

---

# Anexo B. Cambios hechos en el código (para quien mantenga los scripts)

**Nuevos:**
- `orquestacion/flujos.py`: un flujo de Prefect por cada `.bat`. Los `paradox-*` hacen, por cada tabla, tres tareas: `descargar-paradox` → `leer-paradox` → `sincronizar-sql`. Los `compras-*` ejecutan el script correspondiente como una tarea.

**Modificados:**
- `comun/paradox_sync.py`: `procesar()` se divide en `paso_descargar`, `paso_leer` y `paso_sincronizar` para que Prefect muestre cuál falla. `procesar()` sigue existiendo, así que los `.bat` de Windows funcionan igual.
- `Compras/*.py`: antes, si fallaban, mostraban el error pero terminaban "bien", y nadie se enteraba. Ahora, tras deshacer los cambios (rollback), **informan del error**. Se corrigieron además un error que tapaba el mensaje real (`today_date` sin definir) y una división por cero.

**Cómo se gestionan los errores:**
- La descarga de Paradox se reintenta **3 veces, cada 60 s**, por si hay cortes de red.
- La escritura en SQL Server se reintenta **1 vez a los 120 s**. Es seguro porque cada tabla va en su propia transacción.
- Si una tabla Paradox llega **vacía**, el proceso falla en lugar de vaciar la tabla de SQL Server (protección nueva).
- Si una tabla falla, las demás del mismo proceso se siguen sincronizando, y al final el proceso queda en **Failed** con la lista de tablas que fallaron.
- Los `print()` de los scripts aparecen en los logs del dashboard.

**Nombres de las ejecuciones:** `<proceso>-<fecha programada en hora de Madrid>`. Prefect crea por adelantado unas 3 ejecuciones por proceso con nombre aleatorio; al terminar, cada proceso renombra las suyas con su fecha.

**Contenido de `despliegue/docker-compose.yml`** (referencia):

```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: prefect-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 10

  prefect-server:
    image: prefecthq/prefect:${PREFECT_VERSION}-python3.12
    container_name: prefect-server
    restart: unless-stopped
    command: prefect server start --host 0.0.0.0 --port 4200
    environment:
      PREFECT_API_DATABASE_CONNECTION_URL: postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      PREFECT_UI_API_URL: http://${SERVER_IP}:4200/api
      PREFECT_UI_URL: http://${SERVER_IP}:4200
      PREFECT_SERVER_API_AUTH_STRING: ${PREFECT_AUTH_STRING}
      PREFECT_SERVER_ANALYTICS_ENABLED: "false"
      PREFECT_SERVER_SERVICES_DB_VACUUM_ENABLED: "true"
      PREFECT_SERVER_SERVICES_DB_VACUUM_RETENTION_PERIOD: ${RETENCION_DIAS:-90}d
      TZ: ${TZ:-Europe/Madrid}
    ports:
      - "4200:4200"
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:4200/api/health')"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s

volumes:
  postgres_data:
```

- PostgreSQL no se publica fuera de Docker: solo lo ve el servidor de Prefect.
- `PREFECT_SERVER_API_AUTH_STRING` obliga a usar contraseña en el dashboard y en la API.
- `PREFECT_UI_API_URL` y `PREFECT_UI_URL` dependen de `SERVER_IP`: por eso debe coincidir con la IP real.
- El historial de más de 90 días se borra automáticamente.
