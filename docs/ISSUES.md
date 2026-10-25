# Issues — Reproductor de video distribuido

Stack: Python 3.12 · sockets TCP + `threading` (servidor) · `asyncio` (cliente) · Celery + Redis · PostgreSQL · ffmpeg · Docker Compose · Docker SDK (supervisor).
Calidades: **480p / 720p** · Segmentos: **4 s** (MPEG-TS) · Transcodificación on-demand con prefetch.

**Flujo tipo YouTube:** el usuario **sube un video propio** desde su máquina → el servidor lo guarda en el volumen y lo registra en la BD → se analiza en segundo plano → cuando queda en estado `ready` aparece en el catálogo → cualquier usuario lo **elige del listado** y lo reproduce.

---

## 1. Infraestructura

### #1 Estructura de carpetas del repositorio
**Descripción:** Crear `common/`, `server/`, `worker/`, `supervisor/`, `client/`, `db/`, `docs/` y `tests/`, cada una con su `__init__.py`.
**Criterios de aceptación:**
- La estructura existe y se puede importar como paquetes.

### #2 Dependencias del proyecto
**Descripción:** `requirements.txt` con celery, redis, psycopg[pool], docker, pytest y fakeredis, con las versiones fijadas.
**Criterios de aceptación:**
- `pip install -r requirements.txt` funciona en un entorno limpio.

### #3 .gitignore para Python y datos locales
**Descripción:** Ignorar `__pycache__`, `.venv`, `.env` y cualquier archivo de video local.
**Criterios de aceptación:**
- `git status` no muestra archivos generados ni videos.

### #4 Dockerfile de la aplicación
**Descripción:** Una sola imagen (Python 3.12-slim + ffmpeg + dependencias) que comparten server, worker y supervisor.
**Criterios de aceptación:**
- `docker build -t videoapp .` termina sin errores.
- `ffmpeg` y `ffprobe` están disponibles dentro de la imagen.

### #5 Módulo de configuración
**Descripción:** `common/config.py` lee las variables de entorno (Redis, Postgres, puerto, `SEG_LEN=4`, `QUALITIES=480,720`, `PREFETCH`, `MAX_CLIENTS`, `MAX_UPLOAD_MB`), cada una con su valor por defecto.
**Criterios de aceptación:**
- Una variable faltante usa el valor por defecto.
- Un valor inválido falla con un mensaje claro.

### #6 Archivo .env.example
**Descripción:** Documentar cada variable de entorno con un valor de ejemplo.
**Criterios de aceptación:**
- Copiar el archivo a `.env` alcanza para levantar el sistema.

### #7 Tabla `users`
**Descripción:** En `db/init.sql`: id, username (único), password_hash, created_at.
**Criterios de aceptación:**
- Insertar un username duplicado falla por la restricción de unicidad.

### #8 Tabla `videos`
**Descripción:** En `db/init.sql`: id UUID, owner_id (FK a users), title, original_filename, path, size_bytes, duration_s, width, height, status (`uploading|processing|ready|error`), created_at.
**Criterios de aceptación:**
- `status` solo acepta los valores permitidos.
- Existe un índice sobre `status`.

### #9 Servicios postgres y redis en compose
**Descripción:** En `docker-compose.yml`: Postgres con el volumen `pgdata` y el `init.sql` montado, y Redis con `maxmemory` y la política `allkeys-lru`.
**Criterios de aceptación:**
- Los dos servicios levantan y pasan su healthcheck.

### #10 Servicio server en compose
**Descripción:** Servicio `server` que expone el puerto 9000, monta el volumen `videos` con lectura y escritura y depende de que postgres y redis estén sanos.
**Criterios de aceptación:**
- El servidor acepta conexiones desde el host.

### #11 Servicio worker base en compose
**Descripción:** Servicio `worker` con 1 réplica fija, que monta `videos` en solo lectura y consume las colas `urgent` y `prefetch`.
**Criterios de aceptación:**
- El worker aparece conectado en los logs de Celery.

### #12 Servicio supervisor en compose
**Descripción:** Servicio `supervisor` que monta `/var/run/docker.sock` y recibe `MIN_WORKERS`, `MAX_WORKERS` y `TASKS_PER_WORKER`.
**Criterios de aceptación:**
- Desde el contenedor, el supervisor puede listar contenedores con el Docker SDK.

---

## 2. Protocolo

### #13 Envío de mensajes (sync)
**Descripción:** `send_msg(sock, header, payload)`: prefijo de 4 bytes con el largo, header JSON (incluye `size`) y payload binario.
**Criterios de aceptación:**
- Usa `sendall`, así que no quedan envíos parciales.

### #14 Recepción exacta de bytes (sync)
**Descripción:** `_recv_exact(sock, n)` repite `recv` hasta completar `n` bytes y lanza `ConnectionError` si el socket se cierra antes.
**Criterios de aceptación:**
- Maneja correctamente las lecturas fragmentadas.

### #15 Recepción de mensajes (sync)
**Descripción:** `recv_msg(sock)` lee el prefijo, después el header y después el payload, y devuelve `(header, payload)`.
**Criterios de aceptación:**
- Un header JSON inválido lanza un error de protocolo.

### #16 Envío y recepción async
**Descripción:** `async_send_msg` y `async_recv_msg` sobre `StreamWriter` y `StreamReader`, con el mismo formato que la versión sync.
**Criterios de aceptación:**
- Las versiones sync y async son compatibles entre sí.

### #17 Tests del protocolo
**Descripción:** Tests con `socketpair()` que cubran mensajes vacíos, payloads grandes, varios mensajes seguidos, conexión cortada y compatibilidad sync↔async.
**Criterios de aceptación:**
- `pytest tests/test_protocol.py` pasa.

### #18 Documento de especificación del protocolo
**Descripción:** `docs/protocol.md` con cada comando: campos del request, del response y códigos de error.
**Criterios de aceptación:**
- Todos los comandos que implementa el servidor están documentados.

---

## 3. Servidor — núcleo

### #19 Socket de escucha
**Descripción:** Crear el socket TCP con `SO_REUSEADDR`, hacer `bind` al puerto configurado y `listen`.
**Criterios de aceptación:**
- Si el servidor se reinicia, no aparece el error "address already in use".

### #20 Un hilo por cliente
**Descripción:** Loop de `accept()` que lanza un `threading.Thread` por cada conexión nueva.
**Criterios de aceptación:**
- Dos clientes conectados a la vez se atienden en paralelo.

### #21 Límite de clientes simultáneos
**Descripción:** Usar un `threading.Semaphore(MAX_CLIENTS)`. Si se supera el límite, se responde `ERROR busy` y se cierra la conexión.
**Criterios de aceptación:**
- El cliente número `MAX_CLIENTS + 1` recibe el error.

### #22 Apagado ordenado
**Descripción:** Manejar `SIGTERM` y `SIGINT`: dejar de aceptar conexiones, avisar a los hilos y cerrar los sockets.
**Criterios de aceptación:**
- `docker compose stop server` termina en menos de 10 s y sin stacktraces.

### #23 ClientHandler y despacho de comandos
**Descripción:** Clase que guarda la sesión del cliente y despacha cada comando a su método `cmd_<nombre>`. Un comando desconocido devuelve `ERROR`.
**Criterios de aceptación:**
- Una excepción dentro de un comando no mata el hilo.

### #24 Comando BYE y desconexión
**Descripción:** Cerrar la conexión prolijamente cuando llega `BYE` o cuando el cliente se corta, y liberar el semáforo.
**Criterios de aceptación:**
- No quedan hilos ni sockets colgados después de desconectar.

### #25 Logging del servidor
**Descripción:** Logs con timestamp, nombre del hilo y usuario en cada comando recibido.
**Criterios de aceptación:**
- En los logs se distingue la actividad de cada cliente.

### #26 Pool de conexiones a la BD
**Descripción:** `server/db.py` con un `ConnectionPool` compartido entre hilos, que reintenta la conexión al arrancar.
**Criterios de aceptación:**
- Cada hilo toma su propia conexión del pool.

---

## 4. Usuarios

### #27 Hash y verificación de passwords
**Descripción:** `hash_password` y `verify_password` con `hashlib.scrypt`, salt aleatorio y comparación con `hmac.compare_digest`.
**Criterios de aceptación:**
- Hay tests para password correcta, incorrecta y para que dos hashes de la misma password sean distintos.

### #28 Queries de usuarios
**Descripción:** `create_user(username, hash)` y `get_user_by_username(username)` en `db.py`.
**Criterios de aceptación:**
- Crear un usuario duplicado lanza una excepción propia (`UserExists`).

### #29 Validación de credenciales
**Descripción:** El username debe tener entre 3 y 32 caracteres alfanuméricos o `_`. La password debe tener al menos 6 caracteres.
**Criterios de aceptación:**
- Una entrada inválida devuelve `ERROR` con el motivo.

### #30 Comando REGISTER
**Descripción:** Valida los datos, hashea la password y crea el usuario.
**Criterios de aceptación:**
- Responde `OK`, o `ERROR user_exists` si el usuario ya existe, o `ERROR invalid`.

### #31 Comando LOGIN
**Descripción:** Busca el usuario, verifica la password y, si es correcta, guarda el usuario en la sesión del handler.
**Criterios de aceptación:**
- Si las credenciales son incorrectas, responde `ERROR auth`.

### #32 Decorador @requires_auth
**Descripción:** Bloquea los comandos protegidos cuando la sesión no tiene un usuario logueado.
**Criterios de aceptación:**
- Sin login, `UPLOAD_BEGIN` y `PLAY` responden `ERROR unauthorized`.

### #33 Comando LOGOUT
**Descripción:** Limpia el usuario de la sesión sin cerrar la conexión.
**Criterios de aceptación:**
- Después de `LOGOUT`, los comandos protegidos vuelven a fallar.

---

## 5. Subida de videos

### #34 Directorio de almacenamiento
**Descripción:** `server/storage.py` resuelve las rutas `/data/videos/<uuid>.<ext>` y crea el directorio si no existe.
**Criterios de aceptación:**
- Las rutas se generan a partir del UUID y nunca a partir del nombre que manda el cliente (así no se puede hacer path traversal).

### #35 Validación previa del upload
**Descripción:** En `UPLOAD_BEGIN` se valida que la extensión esté permitida (mp4, mkv, webm, mov, avi), que el tamaño declarado no supere `MAX_UPLOAD_MB` y que el título no esté vacío.
**Criterios de aceptación:**
- Un archivo inválido se rechaza antes de recibir cualquier byte.

### #36 Comando UPLOAD_BEGIN
**Descripción:** Crea el registro en la BD con `status=uploading`, abre el archivo `.part` y responde con el `video_id`.
**Criterios de aceptación:**
- El handler queda en modo upload, con el archivo abierto y el contador de bytes en 0.

### #37 Comando UPLOAD_CHUNK
**Descripción:** Escribe el payload en el `.part` y acumula los bytes recibidos.
**Criterios de aceptación:**
- Si se supera el tamaño declarado, el upload se aborta.
- El archivo nunca se carga entero en memoria.

### #38 Comando UPLOAD_END
**Descripción:** Verifica que los bytes recibidos coincidan con el tamaño declarado, renombra el `.part` al nombre final y pone `status=processing`.
**Criterios de aceptación:**
- Si el tamaño no coincide, se responde `ERROR` y se ejecuta la limpieza (#39).

### #39 Limpieza de uploads incompletos
**Descripción:** Si el cliente se desconecta o el upload se aborta, se borra el `.part` y el registro de la BD.
**Criterios de aceptación:**
- No quedan archivos huérfanos ni registros en estado `uploading`.

### #40 Encolar el análisis después del upload
**Descripción:** Al terminar `UPLOAD_END` se encola la tarea `probe_video(video_id)`.
**Criterios de aceptación:**
- La tarea aparece en la cola de Celery con el id correcto.

---

## 6. Catálogo

### #41 Query de videos listos
**Descripción:** `list_ready_videos()` devuelve id, título, duración, dueño, fecha y calidades disponibles de los videos con `status=ready`, ordenados por fecha descendente.
**Criterios de aceptación:**
- Los videos en `processing` o `error` no aparecen.

### #42 Comando LIST
**Descripción:** Devuelve el catálogo público de videos listos.
**Criterios de aceptación:**
- Muestra los videos de todos los usuarios.

### #43 Comando MY_VIDEOS
**Descripción:** Lista los videos del usuario logueado en cualquier estado, para que pueda seguir si su upload todavía se está procesando o si falló.
**Criterios de aceptación:**
- Requiere login y solo muestra los videos propios.

### #44 Comando VIDEO_INFO
**Descripción:** Devuelve el detalle de un video por id: título, duración, resolución, calidades y cantidad de segmentos.
**Criterios de aceptación:**
- Un id inexistente responde `ERROR not_found`.

---

## 7. Workers — análisis

### #45 Configuración de la app Celery
**Descripción:** `worker/celery_app.py` con Redis como broker y backend, las colas `default`, `urgent` y `prefetch`, `prefetch_multiplier=1`, `acks_late` y `reject_on_worker_lost`.
**Criterios de aceptación:**
- Los workers toman de a una tarea por vez.

### #46 Tarea probe_video: lectura de metadata
**Descripción:** Ejecuta `ffprobe -print_format json` sobre el archivo y extrae la duración, el ancho, el alto y si tiene stream de video.
**Criterios de aceptación:**
- Un archivo sin stream de video se marca como inválido.

### #47 Calidades disponibles según la resolución original
**Descripción:** Función pura que, a partir del alto del video original, decide qué calidades ofrecer: 720 solo si el original mide al menos 720px, y 480 siempre.
**Criterios de aceptación:**
- Tests para originales de 360p, 480p, 720p y 1080p.

### #48 Guardar el resultado del análisis
**Descripción:** Guardar duración y resolución en la BD y pasar a `status=ready`, o a `status=error` si el análisis falló.
**Criterios de aceptación:**
- Un archivo corrupto termina en `error` y no deja la tarea colgada.

---

## 8. Workers — transcodificación

### #49 Construcción del comando ffmpeg por segmento
**Descripción:** Función pura que arma los argumentos de ffmpeg: `-ss`, `-t 4`, `scale=-2:{q}`, libx264 veryfast, aac, `-output_ts_offset`, `-f mpegts pipe:1`.
**Criterios de aceptación:**
- Hay tests unitarios de los argumentos generados.

### #50 Tarea transcode_segment
**Descripción:** Ejecuta ffmpeg con `subprocess`, captura los bytes del segmento y los guarda en `seg:{vid}:{q}:{i}` con TTL.
**Criterios de aceptación:**
- Al concatenar segmentos consecutivos, la reproducción es continua.

### #51 Notificar que un segmento está listo
**Descripción:** Después de guardar el segmento, hacer `RPUSH ready:{vid}:{q}:{i}` para despertar al hilo que lo está esperando.
**Criterios de aceptación:**
- El hilo que espera se despierta sin hacer polling activo.

### #52 Manejo de errores de transcodificación
**Descripción:** Si ffmpeg falla, se libera el lock del segmento y se publica un marcador de error para que el hilo que espera no quede bloqueado.
**Criterios de aceptación:**
- El servidor recibe el error y se lo informa al cliente.

### #53 Heartbeat de los workers
**Descripción:** Cada worker publica `worker:{hostname}` con TTL y la cantidad de tareas procesadas.
**Criterios de aceptación:**
- Un worker caído desaparece de Redis cuando vence el TTL.

### #54 Log de distribución de segmentos
**Descripción:** Loguear `worker=X video=Y q=Z seg=i tiempo=Nms` por cada segmento procesado.
**Criterios de aceptación:**
- En los logs se ve que segmentos consecutivos los procesan workers distintos.

---

## 9. Servidor — reproducción

### #55 Cálculo de segmentos
**Descripción:** Función pura que, dada una duración, devuelve la cantidad de segmentos de 4 s (el último puede durar menos).
**Criterios de aceptación:**
- Tests con duraciones exactas, no exactas y menores a 4 s.

### #56 Lock de segmento en Redis
**Descripción:** `try_lock_segment(vid, q, i)` con `SET NX EX 60`.
**Criterios de aceptación:**
- Si dos hilos intentan tomar el mismo lock, solo uno lo obtiene (test con fakeredis).

### #57 Encolado deduplicado de segmentos
**Descripción:** `ensure_enqueued(vid, q, i, queue)`: si el segmento está en cache no hace nada; si no, toma el lock y encola la tarea.
**Criterios de aceptación:**
- Si N clientes piden el mismo segmento, se encola una sola tarea.

### #58 Espera de segmento con timeout
**Descripción:** `wait_segment(vid, q, i, timeout)` usa `BLPOP` sobre `ready:...` y después lee el segmento de la cache.
**Criterios de aceptación:**
- Si se agota el timeout o llega el marcador de error, lanza una excepción.

### #59 Validación del comando PLAY
**Descripción:** Verificar que el video exista, que esté en `ready`, que la calidad pedida esté disponible para ese video y que `start_segment` esté en rango.
**Criterios de aceptación:**
- Cada caso inválido responde con un error específico.

### #60 Respuesta inicial de PLAY
**Descripción:** Enviar `OK {segments, seg_len, quality}` antes de empezar a mandar segmentos.
**Criterios de aceptación:**
- El cliente sabe cuántos segmentos va a recibir.

### #61 Prefetch de los segmentos siguientes
**Descripción:** Por cada segmento `i`, encolar `i` en la cola `urgent` y de `i+1` a `i+PREFETCH` en la cola `prefetch`.
**Criterios de aceptación:**
- Con 1 cliente mirando, los workers ya están procesando segmentos que todavía no se pidieron.

### #62 Envío de segmentos al cliente
**Descripción:** Loop que espera cada segmento, lo envía como `SEGMENT {index}` con su payload y al final manda `END`.
**Criterios de aceptación:**
- Si el cliente se desconecta en medio de la reproducción, el loop termina sin errores.

---

## 10. Supervisor

### #63 Lectura de métricas de carga
**Descripción:** Leer `LLEN` de las colas `urgent` y `prefetch` y contar los workers vivos a partir de los heartbeats.
**Criterios de aceptación:**
- Devuelve un objeto con `pending` y `workers`.

### #64 Cálculo de workers deseados
**Descripción:** Función pura `desired_workers(pending, cfg)` que hace `ceil(pending / TASKS_PER_WORKER)` limitado entre el mínimo y el máximo.
**Criterios de aceptación:**
- Tests para cola vacía, carga media y tope máximo.

### #65 Histéresis y cooldown
**Descripción:** Se sube rápido pero se baja de a un worker por vez, y no se baja durante los X segundos siguientes a una subida.
**Criterios de aceptación:**
- Hay tests que muestran que la cantidad de workers no oscila.

### #66 Descubrir la red y el volumen del compose
**Descripción:** Detectar la red y el volumen `videos` a partir de las labels del propio contenedor del supervisor.
**Criterios de aceptación:**
- Funciona sin nombres hardcodeados.

### #67 Crear un worker dinámico
**Descripción:** `spawn_worker()` lanza un contenedor `videoapp:latest` con un nombre único, la label `videoapp.role=worker-dyn`, la red y el volumen.
**Criterios de aceptación:**
- El worker nuevo empieza a consumir tareas.

### #68 Listar los workers dinámicos
**Descripción:** Listar los contenedores con la label `worker-dyn`, para que el supervisor recupere su estado si se reinicia.
**Criterios de aceptación:**
- Después de reiniciar el supervisor, sigue contando bien los workers existentes.

### #69 Eliminar un worker dinámico
**Descripción:** `remove_worker(name)` le manda un `shutdown` por Celery, espera a que termine la tarea en curso y después borra el contenedor.
**Criterios de aceptación:**
- No se pierde ninguna tarea.
- Nunca se elimina el worker base.

### #70 Loop del supervisor
**Descripción:** Cada 2 s: leer las métricas, calcular la cantidad deseada y crear o eliminar la diferencia.
**Criterios de aceptación:**
- Con carga sube workers, y sin carga vuelve a `MIN_WORKERS`.

### #71 Publicar métricas del supervisor
**Descripción:** Guardar `metrics:supervisor` en Redis (workers, colas, última decisión) y loguear cada cambio (`queue=37 workers 2→6`).
**Criterios de aceptación:**
- Las métricas se actualizan en cada ciclo.

### #72 Comando STATUS en el servidor
**Descripción:** Devuelve `metrics:supervisor` al cliente.
**Criterios de aceptación:**
- Si el supervisor no está corriendo, responde con valores vacíos.

---

## 11. Cliente (asyncio)

### #73 Clase de conexión async
**Descripción:** `connect`, `request(header, payload)` y `close` sobre `asyncio.open_connection`, usando el framing async.
**Criterios de aceptación:**
- Un `ERROR` del servidor se convierte en una excepción `ServerError`.

### #74 Esqueleto de la CLI
**Descripción:** `argparse` con subcomandos que se ejecutan con `asyncio.run`, más las opciones globales `--host` y `--port`.
**Criterios de aceptación:**
- `--help` muestra todos los subcomandos.

### #75 Comando `register` del cliente
**Descripción:** Pide usuario y password (la password con `getpass`) y envía `REGISTER`.
**Criterios de aceptación:**
- Muestra un mensaje claro tanto si sale bien como si falla.

### #76 Comando `login` y credenciales
**Descripción:** Envía `LOGIN`. Las credenciales salen de flags, variables de entorno o se piden de forma interactiva.
**Criterios de aceptación:**
- Los subcomandos protegidos hacen login automáticamente antes de ejecutarse.

### #77 Lectura del archivo por chunks
**Descripción:** Un generador async que lee el archivo local en bloques de 1 MiB sin bloquear el event loop (`asyncio.to_thread`).
**Criterios de aceptación:**
- El uso de memoria no crece con el tamaño del archivo.

### #78 Comando `upload` del cliente
**Descripción:** `upload <ruta> --title "..."`: valida localmente que el archivo exista y tenga una extensión permitida, y después envía `BEGIN`, los `CHUNK` y `END`.
**Criterios de aceptación:**
- Al terminar muestra el `video_id`.

### #79 Barra de progreso del upload
**Descripción:** Mostrar el porcentaje subido y la velocidad durante el upload.
**Criterios de aceptación:**
- Se actualiza en la misma línea de la terminal.

### #80 Comando `list` del cliente
**Descripción:** Muestra el catálogo en una tabla numerada: título, duración, autor y calidades.
**Criterios de aceptación:**
- Si no hay videos, muestra un mensaje en lugar de una tabla vacía.

### #81 Comando `my-videos` del cliente
**Descripción:** Muestra los videos propios con su estado (`processing`, `ready` o `error`).
**Criterios de aceptación:**
- Permite ver cuándo un upload ya está listo para reproducir.

### #82 Selección interactiva de video
**Descripción:** Comando `browse`: muestra el catálogo, el usuario elige un número y una calidad, y empieza la reproducción.
**Criterios de aceptación:**
- Si se ingresa una opción inválida, se vuelve a preguntar.

### #83 Tarea receptora de segmentos
**Descripción:** Corrutina que lee los `SEGMENT` del servidor y los mete en una `asyncio.Queue` acotada.
**Criterios de aceptación:**
- Si la cola está llena, la recepción se frena (backpressure).

### #84 Lanzar el reproductor externo
**Descripción:** Lanzar `ffplay -i pipe:0` o `mpv -` con `asyncio.create_subprocess_exec`, según `--player`.
**Criterios de aceptación:**
- Si el reproductor no está instalado, se muestra un mensaje claro.

### #85 Tarea reproductora
**Descripción:** Corrutina que saca segmentos de la cola y los escribe en el stdin del reproductor. Empieza después de un buffer inicial de 2 segmentos.
**Criterios de aceptación:**
- La recepción y la reproducción corren de forma concurrente.

### #86 Comando `play` del cliente
**Descripción:** `play <video_id> --quality 480|720 --player ffplay|mpv`: envía `PLAY` y coordina la tarea receptora y la reproductora.
**Criterios de aceptación:**
- El video se reproduce completo.

### #87 Cancelación y cierre limpio
**Descripción:** Si se cierra el reproductor o se presiona Ctrl+C, se cancelan las tareas, se manda `BYE` y se cierra el socket.
**Criterios de aceptación:**
- No quedan procesos ni stacktraces.

---

## 12. Pruebas y documentación

### #88 Prueba de carga async
**Descripción:** `scripts/load_test.py --clients N --video <id>`: lanza N clientes con `asyncio.gather`, cada uno hace `PLAY` y descarta los bytes. Al final muestra la latencia promedio y el p95.
**Criterios de aceptación:**
- Con 15 clientes sobre un video ya subido, el supervisor escala por encima de 1 worker.

### #89 Prueba de punta a punta del flujo de usuario
**Descripción:** Documentar y verificar el flujo completo: register → login → subir un video real → `my-videos` hasta que esté `ready` → `browse` → reproducir.
**Criterios de aceptación:**
- El flujo funciona con videos mp4, mkv y webm reales.

### #90 Prueba de upload inválido
**Descripción:** Verificar que se rechacen una extensión no permitida, un archivo que supera el límite y un archivo corrupto (este último debe terminar en `error`).
**Criterios de aceptación:**
- Ningún caso deja archivos huérfanos.

### #91 Prueba de caída de un worker
**Descripción:** Matar un worker con `docker kill` durante la reproducción y verificar que la tarea se reencola y el video sigue.
**Criterios de aceptación:**
- La reproducción se completa.

### #92 Prueba de multiusuario
**Descripción:** Dos o más usuarios reproduciendo videos distintos (y también el mismo) al mismo tiempo.
**Criterios de aceptación:**
- La reproducción es fluida.
- Los segmentos del mismo video se transcodifican una sola vez (se ve en los logs).

### #93 README: arquitectura
**Descripción:** Diagrama de los componentes y explicación de cómo se reparten los segmentos entre los workers.
**Criterios de aceptación:**
- Explica el rol de cada servicio.

### #94 README: instalación y uso
**Descripción:** Cómo levantar el sistema con compose y cómo usar cada comando del cliente.
**Criterios de aceptación:**
- Alguien sin contexto puede subir y reproducir un video siguiendo el README.

### #95 README: demo de escalado
**Descripción:** Pasos para correr la prueba de carga y observar cómo el supervisor crea y elimina workers.
**Criterios de aceptación:**
- Incluye los comandos para ver los logs y `docker ps` con el filtro de label.
