# Supresión con mensaje y ejecución diaria en MonZabbix

## Qué cambió

La web y el menú de consola ahora suprimen **y agregan un mensaje** en la misma operación:

> Suprimido por superar el tiempo de espera aprobado con el cliente. Plazo aplicado: 14 días.

El plazo mostrado corresponde a los días seleccionados en esa operación. `SUPPRESSION_MESSAGE` en `config.env` permite cambiar la primera frase. En el modo diario se agrega también `AUTO_APPROVAL_REFERENCE` del env. El texto se muestra antes de confirmar en la web y en consola.

Se usa `event.acknowledge` con `action=36` (32 suprimir + 4 agregar mensaje), `suppress_until=0` y `message`. No se suman acciones de cierre, reconocimiento ni cambio de severidad. Se comprueba después la supresión y la presencia del texto en las actualizaciones del evento. Un fallo de verificación se muestra como `NO VERIFICADO`. [API oficial](https://www.zabbix.com/documentation/7.4/en/manual/api/reference/event/acknowledge).

El mensaje aplica a las **próximas supresiones**; no se agregó retroactivamente a las alertas suprimidas antes de este cambio. Verlo en Zabbix: Monitoring → Problems → Show suppressed problems → fecha/hora del evento → historial de actualizaciones. Agregar un mensaje puede activar operaciones de actualización de las acciones existentes; no se modifica la configuración de esas acciones.

## Tres maneras de ejecutarlo

| Modo | Comando desde la carpeta del proyecto | Comportamiento |
| --- | --- | --- |
| Web manual | `python3 iniciar_web.py` | Seleccionar grupo, equipos, severidad, días y eventos en el navegador; confirmar. |
| Consola manual | `python3 main.py --debug` | Seleccionar en el menú y escribir `PERMISOS VERIFICADOS` y `APLICAR`. |
| Diario sin interacción | `python3 ejecutar_automatico.py` | Ejecutar una sola pasada con la política aprobada y salir; el timer programa las siguientes. |

`--debug` agrega logs; no activa datos ficticios. `--demo` es la demostración sin conexión del menú/web. Los modos manuales mantienen su límite `MAX_WRITE_EVENTS` por ejecución. El automático tiene su propio límite diario persistente, `AUTO_MAX_EVENTS_PER_DAY`. El modo diario necesita `DRY_RUN=false` además de una política habilitada. No depende de la web, de las selecciones del navegador ni de que una sesión SSH permanezca abierta una vez instalado el timer.

## Configuración única en config.env

El arranque sin parámetros lee la conexión, el token, los filtros F5 y la política automática de **`config.env`**, en la carpeta del proyecto. No necesita editar `automation.json`. Las variables de entorno del sistema tienen prioridad sobre el archivo. `.venv` es el entorno virtual de Python, no el archivo de configuración.

Este bloque ya se añadió al env local, conservando las credenciales y los demás valores:

```ini
DRY_RUN=false
AUTO_ENABLED=true
AUTO_PERMISSIONS_VERIFIED=true
AUTO_APPROVAL_REFERENCE=Alcance diario autorizado por el operador: BANCO ESTADO, High o superior, hasta 100 eventos por día.
AUTO_GROUP_NAME=BANCO ESTADO
AUTO_HOST_IDS=
AUTO_INCLUDE_IPS=
AUTO_DAYS=14
AUTO_MIN_SEVERITY=4
AUTO_MAX_EVENTS_PER_DAY=100
AUTO_DAILY_AT=00:01
```

- `AUTO_HOST_IDS` vacío incluye todos los equipos accesibles del grupo, también los que se incorporen posteriormente. Para restringir por ID, usar una lista separada por comas.
- `AUTO_INCLUDE_IPS` vacío no restringe por IP. Para seleccionar determinadas IP/subredes: `AUTO_INCLUDE_IPS=192.0.2.10,192.0.2.20,2001:db8::/64`. Son ejemplos; reemplazarlos por IP autorizadas. Se evalúan todas las interfaces configuradas, sin resolver DNS. Un filtro sin coincidencias selecciona cero equipos.
- `AUTO_DAYS=14` exige más de 14 días activos.
- `AUTO_MIN_SEVERITY=4` incluye High y Disaster. No cambia la severidad del evento.
- `AUTO_MAX_EVENTS_PER_DAY=100` limita intentos automáticos por día de Chile. Es independiente de `MAX_WRITE_EVENTS`, utilizado en web/consola manual.
- `AUTO_DAILY_AT=00:01` es la hora de America/Santiago que se utiliza al generar el timer. No hace que un comando ejecutado manualmente espere hasta esa hora.
- `AUTO_ENABLED=false` bloquea el arranque real automático. La referencia y la verificación de permisos documentan la autorización previa, que sustituye las preguntas interactivas de la operación manual.

Se conserva el alcance **F5 Pool/VS**, definido por `F5_NAME_PATTERNS`, `F5_TAGS` y `F5_RESOURCE_PATTERN`. Virtual Address no se agregó a la política automática. La referencia documenta la autorización del operador, no sustituye evidencia contractual del cliente. Si cambia el token, revisar sus permisos para suprimir y agregar mensajes.

El 9 de noviembre de 2026 se validó por lectura que BANCO ESTADO corresponde al groupid 73 con 51 equipos accesibles. No se realizaron supresiones en esa comprobación.

### Ejecutar por consola sin preguntas ni parámetros

En MonZabbix:

```bash
cd /opt/zabbix-automatizaciones/zabbix_f5_alert_manager
.venv/bin/python ejecutar_automatico.py
```

En Windows, para operar desde la carpeta local:

```powershell
python ejecutar_automatico.py
```

**Es una ejecución real inmediata**, no una demostración. Hace una pasada con el env, guarda resultados y termina; no solicita `APLICAR`, ni grupo, ni IP. Si falta configuración o permisos, informa el error y sale. No se ejecutó este comando real durante el desarrollo.

Para revisar candidatos sin escribir, usar `python3 run_daily.py`; este comando también lee el env y siempre prepara un plan cuando no recibe `--apply`. Para logs detallados sin argumentos adicionales, configurar `DEBUG=true` en el env.

Los archivos JSON anteriores quedan como referencia/compatibilidad: solo se usan si se invoca explícitamente `run_daily.py --policy ruta.json`. `ejecutar_automatico.py` y el generador del timer usan exclusivamente el env. Editar el JSON no cambia ese arranque.

## Cómo procesa una pasada

1. Valida la política y resuelve grupos/equipos reales. Si el grupo es ambiguo o falta un host autorizado explícitamente, aborta antes de escribir.
2. Consulta todos los problemas abiertos de los equipos elegidos, sin truncarlos con `limit`.
3. Aplica antigüedad, severidad mínima, filtro F5 y exclusión de problemas suprimidos.
4. Ordena de más antiguo a más reciente y selecciona hasta el límite diario restante.
5. Reconsulta cada evento inmediatamente antes de escribir, registra una reserva persistente y envía supresión + mensaje.
6. Verifica resultado y guarda el detalle en los logs y en el historial visible desde la web.

El máximo de 100 se refiere a **intentos de supresión automática por día de America/Santiago**, incluidos los intentos con respuesta incierta. No son 100 por reinicio ni 100 por grupo. Si hay más eventos elegibles, los demás quedan para días posteriores. La próxima ejecución omite los ya suprimidos.

`runtime/daily_state.json` conserva intentos y contadores entre reinicios. Un evento con intento previo no vuelve a procesarse automáticamente, ni siquiera al día siguiente, para evitar duplicados tras un timeout. Si se retiró una supresión manualmente o un intento quedó incierto, revisar en Zabbix antes de cualquier intervención posterior. No borrar el estado para sortear el límite. Conservar `runtime/` al actualizar o reinstalar el código.

Un bloqueo del sistema operativo evita dos ejecuciones automáticas simultáneas. El límite automático no incluye operaciones manuales de la web/consola; evitar operar manualmente sobre los mismos eventos durante la pasada diaria. No hay garantía de transacción atómica entre consultar y escribir en Zabbix.

## Instalar en RHEL

**Estado de la entrega:** el código, la política y los archivos systemd están preparados localmente. No se ha instalado ni habilitado una tarea en MonZabbix. Copiar archivos al servidor, por sí solo, no programa nada.

Se utiliza un timer de systemd y un servicio `oneshot` que termina tras cada pasada. No configurar además cron para el mismo trabajo. No se reinicia Zabbix ni se cambia `EnableGlobalScripts`. El administrador instala únicamente estas dos unidades del proyecto.

### 1. Copiar y preparar

Actualizar el proyecto en:

```text
/opt/zabbix-automatizaciones/zabbix_f5_alert_manager/
```

Copiar el código actualizado, incluido `ejecutar_automatico.py`, `run_daily.py`, `config/automation.py`, `services/daily.py` y `deployment/prepare_timer.py`. Conservar las credenciales del `config.env` del servidor y añadir el bloque AUTO_ indicado arriba. Preservar cualquier estado `runtime/` existente. No es necesario copiar el JSON anterior.

Como administrador, si faltan directorios:

```bash
sudo install -d -m 0700 -o zbx-alertas -g zbx-alertas /opt/zabbix-automatizaciones/zabbix_f5_alert_manager/runtime
sudo install -d -m 0700 -o zbx-alertas -g zbx-alertas /opt/zabbix-automatizaciones/zabbix_f5_alert_manager/logs
```

Como `zbx-alertas`:

```bash
cd /opt/zabbix-automatizaciones/zabbix_f5_alert_manager
source .venv/bin/activate
chmod 600 config.env
python3 -c 'from zoneinfo import ZoneInfo; print(ZoneInfo("America/Santiago"))'
python3 -m unittest discover -s tests -q
```

Python 3.9+ y la base de zonas horarias `tzdata` del sistema deben estar instalados. La cuenta dedicada debe poder leer el código, el env y la CA, y escribir en `logs/` y `runtime/`. Si la CA está bajo un directorio personal, mover su copia pública a una ruta de confianza accesible al servicio y ajustar `ZBX_CA_FILE`; la unidad protege `/home`.

### 2. Validar solo lectura y revisar candidatos

```bash
python3 main.py --check --read-only
python3 run_daily.py --debug
```

El segundo comando **solo prepara un plan**, aunque `DRY_RUN=false` en el env; no envía escrituras ni consume el cupo diario. La política debe tener grupo, hora y criterios válidos. Revisar las entradas AUTO PLAN en la web o en logs. El comando con `--apply` sí escribe hasta el límite aprobado, por lo que no se incluye como prueba de conectividad.

### 3. Generar y revisar unidades

```bash
python3 deployment/prepare_timer.py
cat deployment/generated/zabbix-f5-daily.service
cat deployment/generated/zabbix-f5-daily.timer
systemd-analyze calendar '*-*-* 00:01:00 America/Santiago'
systemd-analyze verify deployment/generated/zabbix-f5-daily.service deployment/generated/zabbix-f5-daily.timer
```

El generador no instala ni activa nada. Las unidades generadas usan la cuenta `zbx-alertas`, el Python de `.venv`, la ruta objetivo y la hora `AUTO_DAILY_AT` de `config.env`. La validación final de systemd se hace en RHEL; no se pudo ejecutar desde el entorno Windows de desarrollo.

### 4. Instalar y activar el horario real

Después de la validación anterior y con `DRY_RUN=false`, instalar como administrador:

```bash
sudo install -m 0644 deployment/generated/zabbix-f5-daily.service /etc/systemd/system/zabbix-f5-daily.service
sudo install -m 0644 deployment/generated/zabbix-f5-daily.timer /etc/systemd/system/zabbix-f5-daily.timer
sudo systemctl daemon-reload
sudo systemctl enable --now zabbix-f5-daily.timer
systemctl list-timers zabbix-f5-daily.timer --all
```

Estos comandos habilitan la ejecución real diaria a las **00:01 de America/Santiago**. `AccuracySec=1min` permite un margen de hasta aproximadamente un minuto. `Persistent=false` evita supresiones de recuperación de horario al arrancar el servidor: si estaba apagado a esa hora, espera al próximo horario diario. El servicio no reintenta automáticamente al fallar. [Referencia de timers systemd](https://www.freedesktop.org/software/systemd/man/254/systemd.timer.html).

No ejecutar `systemctl start zabbix-f5-daily.service` salvo que se quiera iniciar una pasada real **en ese momento**. El timer no abre la web ni mantiene una aplicación permanentemente ejecutándose.

### 5. Ver ejecución, cambiar parámetros y detener

```bash
systemctl status zabbix-f5-daily.timer
systemctl status zabbix-f5-daily.service
journalctl -u zabbix-f5-daily.service --since today
```

Después de una pasada correcta, un servicio `oneshot` puede aparecer `inactive (dead)` y el timer seguir `active (waiting)`; no significa que la programación esté detenida.

Los detalles de eventos quedan en `logs/zabbix_f5_debug.log` y `logs/web_audit.jsonl`. Al abrir la web desde ese mismo directorio, el Registro de actividad muestra AUTO INTENTO, AUTO RESULTADO, AUTO FIN y AUTO ERROR. El diario systemd también registra errores de arranque. Códigos de salida: 0 pasada/plan sin fallos, 1 configuración/conexión/ejecución fallida, 2 uno o más resultados fallidos o no verificados.

Cambiar IP, días, severidad o límite en `config.env` afecta a la siguiente pasada. Cambiar la **hora** requiere volver a generar e instalar el `.timer`, ejecutar `daemon-reload` y reiniciar **solo** `zabbix-f5-daily.timer`.

Para detener futuras ejecuciones:

```bash
sudo systemctl disable --now zabbix-f5-daily.timer
```

También puede poner `AUTO_ENABLED=false` en `config.env`, lo que bloquea futuras escrituras automáticas. Detener el timer no interrumpe una pasada que ya esté en curso. Si se debe interrumpir, `sudo systemctl stop zabbix-f5-daily.service`; después comprobar cualquier intento pendiente en Zabbix. Ninguna de estas acciones deshace supresiones que ya se aplicaron.
