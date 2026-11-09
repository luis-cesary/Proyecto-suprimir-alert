# Supimir — gestión manual de alertas F5 de Zabbix 7.4

> **Consola sin parámetros:** `python ejecutar_automatico.py` realiza una pasada real leyendo todo desde `config.env`. Para la programación diaria y las variables `AUTO_`, consultar [AUTOMATIZACION.md](AUTOMATIZACION.md). No utiliza el JSON anterior por defecto.

> **Actualización:** la web y la consola agregan un mensaje al suprimir. La ejecución diaria para BANCO ESTADO (00:01 Chile, High/Disaster, límite configurable 100) y su instalación están descritas en [AUTOMATIZACION.md](AUTOMATIZACION.md). El timer está preparado, no instalado en MonZabbix.

Aplicación Python con **vista web local y menú de terminal** para consultar problemas abiertos, identificar alertas High de Pools/Virtual Servers F5 con antigüedad superior al umbral elegido y suprimir eventos concretos previa confirmación. Arranca en **simulación / solo lectura**. No se ha conectado ni probado contra MonZabbix durante el desarrollo.

## Inicio rápido de la vista web

Desde la carpeta del proyecto, ejecutar:

```powershell
python main.py --web --demo --debug
```

Abrir **http://127.0.0.1:8080** en el navegador. La terminal debe permanecer abierta; `Ctrl+C` detiene el servidor. No requiere dependencias adicionales, token ni archivo env para la demo. Si el puerto está ocupado, agregar `--port 8081` y abrir esa dirección.

1. Elegir un cliente en **Grupo de hosts en Zabbix**. El cliente corresponde al grupo; no se mantiene un catálogo separado.
2. Seleccionar equipos individualmente o con **Seleccionar visibles**. Se muestran nombres, IP, DNS y estado habilitado/deshabilitado.
3. Opcionalmente filtrar por IP, IP separadas por comas o CIDR. **Filtrar** selecciona las coincidencias y reemplaza la selección previa; **Ver todos** muestra nuevamente todos los hosts sin alterar la selección. Desmarcar un equipo lo excluye.
4. Elegir **severidad** (Sin clasificar, Información, Warning, Average, High o Disaster), días y pulsar **Consultar alertas**. High sigue siendo el valor predeterminado. **Elegibles** muestra los eventos aptos para la severidad elegida; **Todas** también muestra los descartados y sus motivos. El CSV exporta todos los problemas de la consulta.
5. Marcar uno o varios eventos y **Revisar selección**. El diálogo muestra los Event ID y nombres exactos. Escribir `APLICAR`; en demo se registra una **SIMULACIÓN: sin escritura**, no una supresión real.
6. Revisar **Registro de actividad**: cliente, host, evento, hora, modo y resultado. Se actualiza cada cinco segundos mientras la pestaña está visible. Expandir **Ver logs de depuración** para revisar filtros y llamadas API.

La consulta no se repite automáticamente: el botón **Actualizar consulta** permite hacerlo manualmente. Cambiar grupo, equipos, severidad o días invalida la selección de eventos anterior. El servidor conserva la severidad de la consulta y vuelve a comprobarla antes de suprimir; seleccionar una severidad nunca modifica la severidad del evento en Zabbix. Tras confirmar, la consulta queda consumida y es necesario volver a consultar antes de una nueva operación. Una recarga del navegador inicia una selección visual vacía.

### Datos reales, inicialmente solo lectura

Para abrir directamente la web con Zabbix real y logs, ejecutar `python iniciar_web.py` o abrir ese archivo en PyCharm y pulsar Run/Debug, sin parámetros. Usa `config.env` y respeta `DRY_RUN` (mantener `true` para probar sin escrituras). Este arranque no activa datos ficticios.

Configurar `config.env` como se explica más adelante y ejecutar:

```bash
python3 main.py --web --read-only --debug
```

El token solo se usa en Python para conectar a la API; nunca se entrega al navegador. No se incorporan usuarios, login, roles ni privilegios locales. Por esa razón el servidor escucha exclusivamente en **127.0.0.1** y está pensado para un operador local o mediante túnel SSH. No exponerlo mediante proxy público o red compartida. No crea servicios ni tareas en segundo plano.

`--debug` solamente activa logs: permite trabajar con datos reales de Zabbix. `--demo` sustituye Zabbix por datos ficticios. En PyCharm, usar **Run → Edit Configurations → Parameters** con `--web --read-only --debug`, y pulsar Debug para detenerse en breakpoints. No forzar `args.demo = True` en el código: eso impide usar datos reales incluso teniendo token configurado. La versión ejecutada con y sin el depurador usa el mismo flujo de selección y supresión.

`DEFAULT_SEVERITY` en `config.env` acepta valores de 0 a 5 y determina la selección inicial. La web permite cambiarla por consulta sin editar el archivo. El filtro F5 y la antigüedad siguen aplicándose, además de la severidad elegida.

### Ver desde tu PC una ejecución en MonZabbix

En MonZabbix, como la cuenta Linux dedicada:

```bash
cd /opt/zabbix-automatizaciones/zabbix_f5_alert_manager
source .venv/bin/activate
python3 main.py --web --read-only --debug
```

En otra terminal de tu PC, mantener abierto el túnel SSH con tu cuenta autorizada:

```powershell
ssh -N -L 8080:127.0.0.1:8080 TU_USUARIO_SSH@MonZabbix
```

Abrir **http://127.0.0.1:8080** en tu PC. Si ya usas ese puerto, iniciar el servidor con `--port 8081`, usar el túnel `ssh -N -L 8081:127.0.0.1:8081 TU_USUARIO_SSH@MonZabbix` y navegar a `http://127.0.0.1:8081`. El servidor valida el puerto Host: mantener iguales los puertos del navegador y del servidor. No modificar el firewall de Zabbix ni abrir puertos externos para este panel.

### Supresión real desde la web

Completar primero las comprobaciones de la sección de segunda etapa, configurar `DRY_RUN=false` y `MAX_WRITE_EVENTS=1`, y ejecutar `python3 main.py --web --debug` sin `--read-only`. El diálogo exige `PERMISOS VERIFICADOS` y `APLICAR`. Se aplica la misma revalidación y verificación posterior del menú de terminal. El límite de intentos se comparte entre todas las sesiones y pestañas del proceso; abrir otra pestaña no lo reinicia. Reiniciar el servidor sí inicia una nueva ejecución.

El registro estructurado queda en `logs/web_audit.jsonl` y persiste entre reinicios. La pantalla muestra sus últimas 200 entradas; los logs técnicos muestran las últimas 100 líneas de `logs/zabbix_f5_debug.log`. El historial identifica DEMO, SIMULACIÓN o REAL. Una SOLICITUD sin RESULTADO puede indicar una interrupción: verificar el evento en Zabbix antes de repetir. Conservar o archivar el JSONL según la política local; no tiene rotación automática. Los registros son locales, no una auditoría inmutable ni una identificación de operadores, ya que no existe login.

Las solicitudes de escritura usan comprobación de origen, cookie local HttpOnly/SameSite, token CSRF y un identificador de consulta de un solo uso. La aplicación sirve solo sus tres recursos web y rutas API conocidas, nunca `config.env` ni archivos arbitrarios.

## Arquitectura MVC y alcance

Se tomó como referencia únicamente la organización del proyecto local `E:\proyecto base`: módulos bajo `server/`, con `controllers.py`, `managers.py`, `models.py` y `views/`. No se copió código funcional, configuración, credenciales, usuarios, roles, privilegios, ORM, base de datos ni servidor web. `Supimir` es el nombre de esta aplicación; su carpeta instalable es `zabbix_f5_alert_manager`.

```text
zabbix_f5_alert_manager/
├── main.py
├── config.env.example
├── requirements.txt
├── README.md
├── .gitignore
├── config/settings.py
├── server/alertas/
│   ├── models.py          # Estado y entidades en memoria
│   ├── managers.py        # Composición de servicios
│   ├── controllers.py     # Flujo de interacción y selección
│   ├── web.py            # Controlador HTTP local y registro de actividad
│   └── views/
│       ├── terminal.py   # Vista de terminal
│       └── web/          # index.html, style.css, app.js
├── services/
│   ├── zabbix_api.py      # HTTPS + JSON-RPC, métodos permitidos
│   ├── demo.py            # Datos ficticios; sin transporte de red
│   ├── groups.py
│   ├── hosts.py
│   ├── problems.py
│   └── suppression.py
├── cli/menu.py
├── cli/tables.py
├── utils/logger.py
├── utils/validators.py
├── tests/                # unittest, API simulada
├── logs/.gitkeep
└── exports/.gitkeep
```

No ejecuta SQL ni scripts remotos de Zabbix. La programación diaria opcional usa un timer systemd propio, que se instala por separado. No modifica triggers, ítems, templates, hosts, servicios F5, Media types, InvGate o `EnableGlobalScripts=0`. No requiere reiniciar Zabbix. No implementa login ni autorización local: se utiliza un token de Zabbix con los permisos que su administrador ya haya establecido. El adaptador web local fue añadido por solicitud posterior; el menú original sigue disponible sin `--web`.

**La supresión sí puede alterar la visibilidad y las notificaciones/escalaciones de los eventos seleccionados, incluida su entrega a InvGate según las acciones existentes.** No es posible garantizar notificaciones idénticas al suprimir. En la primera etapa, con `DRY_RUN=true`, no se modifica ningún evento.

## 1. Requisitos en RHEL

Python 3.9 o superior con `ssl`, `venv` y la biblioteca estándar. No hay paquetes Python externos. Acceso HTTPS desde MonZabbix a la API, resolución DNS y confianza en el certificado del frontend. RHEL 9 proporciona Python 3.9; en RHEL 8 el administrador debe instalar una versión compatible disponible en los repositorios de su organización. No sustituir el Python utilizado por el sistema operativo.

Comprobar:

```bash
python3 --version
python3 -c 'import ssl, venv; print(ssl.OPENSSL_VERSION)'
```

Si falta Python, el administrador puede instalar los paquetes aprobados de su versión RHEL, por ejemplo en RHEL 9:

```bash
sudo dnf install python3 python3-pip
```

## 2. Directorios y cuenta Linux dedicada

Una sola vez, con administración Linux (omitir `useradd` si la cuenta ya existe):

```bash
sudo useradd --create-home --shell /bin/bash zbx-alertas
sudo install -d -m 0750 -o zbx-alertas -g zbx-alertas /opt/zabbix-automatizaciones/zabbix_f5_alert_manager
```

Copiar el **contenido** de esta carpeta de entrega a `/opt/zabbix-automatizaciones/zabbix_f5_alert_manager/`. Por ejemplo, desde la carpeta padre de una copia transferida a MonZabbix:

```bash
sudo cp -a zabbix_f5_alert_manager/. /opt/zabbix-automatizaciones/zabbix_f5_alert_manager/
sudo chown -R zbx-alertas:zbx-alertas /opt/zabbix-automatizaciones/zabbix_f5_alert_manager
sudo chmod -R u=rwX,g=rX,o= /opt/zabbix-automatizaciones/zabbix_f5_alert_manager
sudo -iu zbx-alertas
cd /opt/zabbix-automatizaciones/zabbix_f5_alert_manager
umask 077
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

`requirements.txt` no instala dependencias externas; ese paso es opcional. Desde aquí la operación no necesita root. Todos los comandos siguientes se ejecutan desde la carpeta del proyecto con el entorno virtual activado.

## 3. Token API y permisos en Zabbix

En Zabbix 7.4, un administrador puede usar **Users → API tokens**, crear un token asociado al usuario técnico, definir caducidad, mantenerlo habilitado y generar/copiar su valor una sola vez. La cuenta técnica debe tener acceso únicamente a los grupos requeridos. También puede gestionar su token desde sus ajustes de usuario si el rol lo permite. No conceder Super admin para ejecutar esta aplicación.

Métodos de lectura utilizados: `apiinfo.version`, `hostgroup.get`, `host.get`, `problem.get`. La segunda etapa requiere permitir `event.acknowledge` y la acción de suprimir problemas para ese usuario en Zabbix. La aplicación nunca crea ni modifica usuarios o roles.

Antes de escribir, el operador debe confirmar con el administrador esos permisos y escribir `PERMISOS VERIFICADOS` en la aplicación. Se comprueba además la lectura del evento inmediatamente antes de cada escritura. Esto es una confirmación operativa, **no una inspección automática del rol**: una consulta de lectura exitosa no demuestra permiso para suprimir, y no se realiza una escritura de prueba. La API sigue siendo la autoridad final y cualquier rechazo se registra como fallo.

## 4. Configuración protegida

```bash
cp config.env.example config.env
chmod 600 config.env
vi config.env
```

Configurar `ZBX_API_TOKEN` con el valor real sin publicarlo ni escribirlo en comandos que queden en el historial. Mantener:

```ini
ZBX_API_URL=https://sim.itqlatam.com/api_jsonrpc.php
DRY_RUN=true
MAX_WRITE_EVENTS=1
DEFAULT_DAYS=14
DEFAULT_SEVERITY=4
```

El archivo es un formato simple `CLAVE=valor`; no se ejecuta como shell, no hay expansión de variables y los comentarios deben estar en su propia línea. Las variables de entorno tienen prioridad sobre el archivo. `--env /ruta/config.env` selecciona otro archivo. En Linux se rechazan archivos env con permisos de grupo u otros. En Windows restringir el ACL al usuario que opera la aplicación.

Para CA interna, `ZBX_CA_FILE=/ruta/ca-corporativa.pem` debe apuntar a un bundle PEM de confianza. La validación HTTPS siempre está habilitada; no existe opción equivalente a `verify=False`. Se rechazan URLs HTTP, credenciales en URL y redirecciones, evitando enviar el token a otro destino.

## 5. Filtro F5 con nombres reales

Los patrones iniciales son ejemplos conservadores y **deben ajustarse con los nombres/etiquetas reales** observados en su entorno. No se considera cualquier problema High como F5.

Un problema coincide si su nombre satisface una regex de `F5_NAME_PATTERNS`, **o** tiene una etiqueta de `F5_TAGS` y el nombre satisface `F5_RESOURCE_PATTERN`:

```ini
F5_NAME_PATTERNS=(?i)\bF5\b.*\b(pool|virtual server|VS)\b
F5_TAGS=vendor=F5
F5_RESOURCE_PATTERN=(?i)\b(pool|virtual server|VS)\b
```

Separar regex alternativas por `;;` y pares etiqueta=valor por `;`. Las etiquetas se comparan por igualdad sin distinguir mayúsculas. El patrón de nombre debe identificar inequívocamente F5 y un recurso Pool/VS; una regex genérica como `.*` ampliaría indebidamente el alcance. Si el problema real se llama `Pool /Common/app no disponible` sin referencia F5, utilice una etiqueta F5 real o una regex específica validada para ese grupo. No se agregan etiquetas desde esta aplicación.

## 6. Demostración sin conexión

```bash
python3 main.py --demo --debug
```

La demo ignora el archivo env y las credenciales; no crea el cliente de red. Contiene dos grupos ficticios, hosts con IPv4/IPv6, un host DNS sin IP y problemas elegibles/descartados. Siempre permanece en simulación, incluso si el entorno contiene `DRY_RUN=false`.

Recorrido: opción 1 → búsqueda vacía → grupo 1; opción 2 → 3 (todos) → 0; opción 3 (consultar); opción 4 (elegibles); opción 5 → `todos` → `APLICAR` muestra simulación sin escritura; opción 6 exporta CSV; opción 0 sale.

## 7. Prueba de conectividad y modo real de lectura

```bash
python3 main.py --check --read-only --debug
python3 main.py --read-only --debug
```

`--check` comprueba versión 7.4.x y una lectura autenticada de grupos y termina. No confirma permisos de escritura ni demuestra que haya hosts visibles. `--read-only` fuerza simulación aun si `DRY_RUN=false`. Sin este argumento, el valor por defecto sigue siendo `DRY_RUN=true`.

## 8. Selección, consulta y depuración

1. Seleccionar grupo: buscar por nombre, mostrar todos o elegir por número. Para evitar ambigüedad con un índice, usar `id:12345` al seleccionar un groupid. `Banco estado` es un ejemplo, nunca se asume un ID real.
2. Seleccionar equipos: uno, varios por comas, todos, IP exacta, varias IP, CIDR IPv4/IPv6 o exclusión. Cada selección reemplaza la anterior; la exclusión opera sobre la selección actual. Volver con `0` conserva la selección.
3. Se muestran todas las interfaces configuradas. Los hosts sin IP o basados en DNS siguen disponibles para selección por número/todos. El filtro IP compara direcciones configuradas, incluso interfaces secundarias; no resuelve DNS ni inventa direcciones.
4. Consultar: obtiene todos los problemas abiertos de los hosts seleccionados y muestra por defecto solo los elegibles: High, no suprimidos, antigüedad estrictamente mayor que el umbral, alcance F5. El total consultado y cada descarte están disponibles en logs; CSV permite exportar todos los consultados o solo elegibles.
5. Opción 8 cambia días a 7, 14, 30 o cualquier entero positivo. Por defecto son 14. Cambiar grupo, hosts o días invalida resultados y exige una nueva consulta.

La antigüedad se calcula en segundos desde `clock`, sin truncar días para decidir elegibilidad. La fecha de inicio se muestra en UTC; los logs usan la zona horaria del sistema que ejecuta Python. El nombre completo del problema conserva el identificador Pool/VS cuando Zabbix lo incluye; no se inventa un nombre de recurso ausente.

`problem.get` se consulta por host sin `limit` y se deduplica por Event ID; así se asocian hosts sin utilizar un parámetro `selectHosts` no soportado por ese método. Para grupos muy grandes la lectura puede tardar y consumir memoria; no se truncan resultados. Una excepción invalida la consulta en curso. Solo se ven objetos accesibles al token.

Opción 7 muestra las últimas 80 líneas de `logs/zabbix_f5_debug.log`. Con `--debug` también se imprimen métodos, parámetros de filtros, interfaces y motivos de descarte. Rotación: 2 MB por archivo y cinco copias. Tokens y encabezados no se registran. Los logs y CSV pueden incluir nombres e IP internas; permanecen locales y excluidos de Git. Los CSV se crean sin sobrescribir y neutralizan fórmulas provenientes de nombres remotos.

## 9. Segunda etapa: una supresión real controlada

Después de validar lectura, patrones y permisos, salir del programa. En `config.env` cambiar **únicamente** `DRY_RUN=false`, manteniendo `MAX_WRITE_EVENTS=1`. Revisar que no haya variables de entorno que sobrescriban esos valores.

```bash
python3 main.py --debug
```

Seleccionar grupo y equipos, consultar y elegir la opción 5. Elegir **un único evento**, revisar su Event ID/nombre/host y la advertencia. Confirmar los permisos administrativos escribiendo `PERMISOS VERIFICADOS`; escribir exactamente `APLICAR` para confirmar. Cualquier otro texto cancela.

Antes de cada escritura se vuelve a consultar el Event ID restringido a los hosts seleccionados y se valida que siga abierto, con la severidad seleccionada (High por defecto), no suprimido, F5 y con antigüedad superior al umbral actualmente elegido (14 días por defecto). Si desapareció, se recuperó o cambió, se omite. La única llamada de escritura posible tiene este contenido:

```json
{"eventids": ["EVENT_ID"], "action": 36, "suppress_until": 0, "message": "Suprimido por superar el tiempo de espera aprobado con el cliente. Plazo aplicado: 14 días."}
```

Se valida el Event ID devuelto y se vuelve a consultar el estado. Cada evento tiene resultado individual y registro local. Una respuesta inesperada, timeout o imposibilidad de verificar produce resultado no confirmado; **no se reintenta automáticamente**. Ante un timeout, la API podría haber aplicado la operación: comprobar en Zabbix antes de una nueva ejecución.

El límite cuenta **intentos de escritura durante toda la sesión**, incluso intentos fallidos; reiniciar el programa inicia otra sesión. No ejecutar sesiones simultáneas para la primera prueba. Si se seleccionan más eventos que el límite restante, se bloquea la selección completa. Para futuras operaciones múltiples, cambiar el límite solo tras validar la primera prueba; sigue siendo necesaria la confirmación explícita de la selección exacta.

Hay un intervalo inevitable entre lectura y escritura: la API no ofrece una operación atómica de comparación de estos filtros y supresión. Si el evento cambia en ese intervalo, el resultado debe verificarse. No se puede prometer ausencia absoluta de carreras; el programa minimiza el intervalo consultando inmediatamente antes de cada llamada.

Al terminar, volver a `DRY_RUN=true`. La aplicación nunca usa acciones de cierre, reconocimiento, cambio de severidad o deshabilitación. La supresión afecta al evento concreto; no cambia la lógica de recuperación ni la generación normal de nuevos eventos por Zabbix.

## 10. Validación en Monitoring → Problems y reversión

En **Monitoring → Problems**, activar el filtro para mostrar problemas suprimidos, localizar el Event ID y revisar el indicador/historial de supresión. Confirmar que continúa como problema abierto si la condición sigue activa y que el reconocimiento y severidad no cambiaron. Revisar notificaciones y el comportamiento esperado de las acciones existentes con el administrador.

Para deshacer manualmente, abrir la actualización del problema seleccionado y elegir **Unsuppress / Dejar de suprimir**, según el idioma del frontend. No elegir cerrar, reconocer ni cambiar severidad. Si existe mantenimiento u otra causa de supresión, retirar la supresión manual no elimina esas otras causas. Esta versión no envía la acción 64 por API; la reversión se hace en Zabbix. Si el problema se recuperó, revisar su historial en lugar de intentar recrearlo.

## 11. Pruebas automatizadas

```bash
python3 -m unittest discover -s tests -v
python3 main.py --demo --check
```

Todas las llamadas están simuladas; no se usan credenciales reales ni escrituras en producción. Se cubren autenticación, TLS/timeouts, parámetros exactos de supresión, selección, IPv4/IPv6/CIDR/DNS, antigüedad y límites, F5, recuperación previa, simulación, confirmación incorrecta, permisos no confirmados, fallos y verificación posterior, menú, CSV y protección de configuración. Los temporales de pruebas se crean bajo `tests/` y se limpian al finalizar.

## 12. Solución de errores

| Síntoma | Comprobación |
| --- | --- |
| Token ausente o rechazo API | Token generado, habilitado, no caducado y permisos del usuario técnico. No pegar tokens en tickets/logs. |
| HTTP 401/403 | Autenticación, proxy, políticas del frontend y acceso API. |
| HTTP 301/302 | Configurar el endpoint HTTPS final; no se siguen redirecciones. |
| TLS | Cadena CA, nombre del certificado y `ZBX_CA_FILE`; nunca desactivar TLS. |
| Timeout/conexión | DNS, firewall, conectividad y `ZBX_TIMEOUT`; si fue escritura, verificar estado antes de repetir. |
| Grupo vacío/inexistente | Buscar grupos reales y permisos; no asumir el ID de Banco estado. |
| Cero elegibles | Revisar patrones/etiquetas reales, High, antigüedad estricta y supresión existente; exportar consultados. |
| DNS sin coincidencias IP | Seleccionar host por número; el filtro IP no resuelve DNS. |
| config.env rechazado | `chmod 600 config.env`; usuario propietario correcto. |
| Sin permiso en logs/exports | Revisar propietario de la carpeta; ejecutar como cuenta Linux dedicada. |
| Escritura bloqueada | Revisar simulación, `APLICAR`, confirmación de permisos y límite por sesión. |
| NO VERIFICADO | Revisar Event ID en Monitoring → Problems/historial; no asumir éxito ni reintentar a ciegas. |

## Referencias oficiales comprobadas

- [API Zabbix 7.4](https://www.zabbix.com/documentation/7.4/en/manual/api): autenticación Bearer y JSON-RPC.
- [hostgroup.get](https://www.zabbix.com/documentation/7.4/en/manual/api/reference/hostgroup/get): grupos y búsqueda.
- [host.get](https://www.zabbix.com/documentation/7.4/en/manual/api/reference/host/get): groupids e interfaces.
- [problem.get](https://www.zabbix.com/documentation/7.4/en/manual/api/reference/problem/get): problemas abiertos, hostids/eventids, etiquetas y supresión.
- [event.acknowledge](https://www.zabbix.com/documentation/7.4/en/manual/api/reference/event/acknowledge): acción 36 (supresión + mensaje), `suppress_until=0` y resultado eventids.
- [API tokens](https://www.zabbix.com/documentation/7.4/en/manual/web_interface/frontend_sections/users/api_tokens): gestión administrativa de tokens.

La documentación es de la rama 7.4. Se detecta la versión real al conectar; la compatibilidad y permisos específicos de MonZabbix 7.4.16 deben validarse primero en modo lectura.
# Proyecto-suprimir-alert

