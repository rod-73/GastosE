# 04 — Sandbox del worker (GastosE Phase 2)

Diseño de implementación del sandbox del worker de extracción (ADR-0011).
Cubre: contenedor, cgroup, no-root, seccomp, network egress.

**Amenazas cubiertas**: T4 (compromiso del worker), G16..G18.
**ADR**: ADR-0011 (worker en contenedor con límites).
**NFR**: NFR-4 (idempotencia), NFR-6 (rendimiento).

## 1. Contenedor (ADR-0011)

### 1.1 Imagen del worker

- **Base**: `python:3.11-slim` (o equivalente).
- **Tamaño**: < 500 MB.
- **Paquetes**: solo los necesarios (PDF parser, XML parser, OCR, LLM client).
- **No incluir**: shell interactivo, package managers, tools de debugging.

### 1.2 Dockerfile (esquemático)

```dockerfile
FROM python:3.11-slim

# Usuario no-root
RUN useradd --create-home --shell /bin/false gastosE_worker
USER gastosE_worker

# Instalar dependencias
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copiar código
COPY workers/ /app/workers/
WORKDIR /app

# Comando de entrada
CMD ["python", "-m", "workers.extraction"]
```

### 1.3 Permisos del contenedor

- **No-root**: el contenedor se ejecuta como usuario `gastosE_worker`
  (UID 1000).
- **Read-only filesystem**: el filesystem del contenedor es read-only
  (excepto `/tmp` para archivos temporales).
- **No privileges**: no se conceden privilegios adicionales
  (`--cap-drop=ALL`).

## 2. Límites de recursos (cgroup)

### 2.1 CPU

- **Límite**: 2 CPUs (2000 millicores).
- **Configuración**: `--cpus=2` (Docker) o `cpu.max=200000 100000` (cgroup
  v2).

### 2.2 Memoria

- **Límite**: 2 GB.
- **Configuración**: `--memory=2g` (Docker) o `memory.max=2147483648`
  (cgroup v2).
- **OOM handling**: si se excede el límite, el proceso se mata (OOM kill).
  El job se marca como `failed` con `failure_reason = 'OOM'`.

### 2.3 PIDs

- **Límite**: 100 procesos.
- **Configuración**: `--pids-limit=100` (Docker) o `pids.max=100` (cgroup
  v2).
- **Propósito**: prevenir fork bombs.

### 2.4 Timeout

- **Límite**: 300 segundos (5 minutos) por job.
- **Configuración**: `--timeout=300` (Docker) o `cpu.max` + watchdog.
- **Exceso**: el proceso se mata. El job se marca como `failed` con
  `failure_reason = 'timeout'`.

## 3. Seccomp

### 3.1 Perfil seccomp

- **Base**: perfil seccomp de Docker (bloquea syscalls peligrosos).
- **Adicional**: bloquear syscalls específicos:
  - `ptrace` (debugging).
  - `mount` (montar filesystems).
  - `reboot` (reiniciar).
  - `swapon`/`swapoff` (swap).
  - `kexec_load` (cargar kernel).
- **Configuración**: `--security-opt seccomp=profile.json` (Docker).

### 3.2 Perfil seccomp (esquemático)

```json
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "syscalls": [
    {"names": ["read", "write", "open", "close", "stat", "fstat", "lstat", "poll", "lseek", "mmap", "mprotect", "munmap", "brk", "rt_sigaction", "rt_sigprocmask", "rt_sigreturn", "ioctl", "access", "pipe", "select", "sched_yield", "mremap", "msync", "mincore", "mkdir", "rmdir", "utime", "statfs", "fstatfs", "sysinfo", "times", "getrlimit", "getrusage", "umask", "chdir", "fchdir", "rename", "truncate", "ftruncate", "getdents", "getcwd", "link", "unlink", "symlink", "readlink", "chmod", "fchmod", "chown", "fchown", "lchown", "umask", "gettimeofday", "getpid", "getppid", "getuid", "getgid", "geteuid", "getegid", "setpgid", "setsid", "getsid", "capget", "capset", "rt_sigpending", "rt_sigtimedwait", "rt_sigqueueinfo", "rt_sigsuspend", "sigaltstack", "utimes", "madvise", "shmget", "shmat", "shmctl", "shmdt", "msgget", "msgsnd", "msgrcv", "msgctl", "semget", "semop", "semctl", "semtimedop", "nanosleep", "alarm", "setitimer", "getitimer", "getpgrp", "gettid", "readahead", "socket", "connect", "accept", "sendto", "recvfrom", "sendmsg", "recvmsg", "shutdown", "bind", "listen", "getsockname", "getpeername", "socketpair", "setsockopt", "getsockopt", "clone", "fork", "vfork", "execve", "exit", "wait4", "kill", "uname", "semaphore", "semaphore64", "futex", "sched_setaffinity", "sched_getaffinity", "getpriority", "setpriority", "io_setup", "io_destroy", "io_getevents", "io_submit", "io_cancel", "getrlimit", "getrusage", "sysinfo", "times", "getpid", "getppid", "getuid", "getgid", "geteuid", "getegid", "setpgid", "setSID", "getsid", "capget", "capset", "rt_sigpending", "rt_sigtimedwait", "rt_sigqueueinfo", "rt_sigsuspend", "sigaltstack", "utimes", "madvise", "shmget", "shmat", "shmctl", "shmdt", "msgget", "msgsnd", "msgrcv", "msgctl", "semget", "semop", "semctl", "semtimedop", "nanosleep", "alarm", "setitimer", "getitimer", "getpgrp", "gettid", "readahead", "socket", "connect", "accept", "sendto", "recvfrom", "sendmsg", "recvmsg", "shutdown", "bind", "listen", "getsockname", "getpeername", "socketpair", "setsockopt", "getsockopt", "clone", "fork", "vfork", "execve", "exit", "wait4", "kill", "uname", "semaphore", "semaphore64", "futex", "sched_setaffinity", "sched_getaffinity", "getpriority", "setpriority", "io_setup", "io_destroy", "io_getevents", "io_submit", "io_cancel", "getrlimit", "getrusage", "sysinfo", "times", "getpid", "getppid", "getuid", "getgid", "geteuid", "getegid", "setpgid", "setSID", "getsid", "capget", "capset", "rt_sigpending", "rt_sigtimedwait", "rt_sigqueueinfo", "rt_sigsuspend", "sigaltstack", "utimes", "madvise", "shmget", "shmat", "shmctl", "shmdt", "msgget", "msgsnd", "msgrcv", "msgctl", "semget", "semop", "semctl", "semtimedop", "nanosleep", "alarm", "setitimer", "getitimer", "getpgrp", "gettid", "readahead", "socket", "connect", "accept", "sendto", "recvfrom", "sendmsg", "recvmsg", "shutdown", "bind", "listen", "getsockname", "getpeername", "socketpair", "setsockopt", "getsockopt", "clone", "fork", "vfork", "execve", "exit", "wait4", "kill", "uname", "semaphore", "semaphore64", "futex", "sched_setaffinity", "sched_getaffinity", "getpriority", "setpriority", "io_setup", "io_destroy", "io_getevents", "io_submit", "io_cancel"], "action": "SCMP_ACT_ALLOW"},
    {"names": ["ptrace", "mount", "reboot", "swapon", "swapoff", "kexec_load"], "action": "SCMP_ACT_ERRNO"}
  ]
}
```

## 4. Network egress restriction

### 4.1 Regla

- **Por defecto**: sin acceso a red.
- **Excepción**: solo acceso al endpoint del ExtractionLLM (ADR-0010).
- **Configuración**:
  ```yaml
  # docker-compose.yml
  services:
    extraction-worker:
      networks:
        - worker_net  # red dedicada (no "none", para permitir acceso al LLM)
  
  networks:
    worker_net:
      driver: bridge
  ```
- **Firewall**: la red `worker_net` tiene reglas de firewall que solo
  permiten tráfico saliente al endpoint del ExtractionLLM.
  ```bash
  # iptables en el host (esquemático)
  iptables -A OUTPUT -p tcp -d <llm_endpoint_ip> --dport 443 -j ACCEPT
  iptables -A OUTPUT -j DROP
  ```
- **Nota**: `network_mode: "none"` bloquearía también el acceso al LLM. Se
  usa una red dedicada con firewall en su lugar.

### 4.2 Firewall (si se usa red)

- **Regla**: solo permitir tráfico saliente al endpoint del ExtractionLLM.
  ```bash
  # iptables (esquemático)
  iptables -A OUTPUT -p tcp -d <llm_endpoint_ip> --dport 443 -j ACCEPT
  iptables -A OUTPUT -j DROP
  ```
- **DNS**: solo permitir DNS al resolver el endpoint del ExtractionLLM.

### 4.3 Justificación

- El worker no necesita acceso a internet (solo al LLM local).
- Si el worker se compromete, no puede exfiltrar datos a internet.
- El LLM local se ejecuta en el mismo host (o en un contenedor dedicado).

## 5. OOM handling

### 5.1 Detección

- Si el proceso se mata por OOM, el exit code es 137 (SIGKILL).
- El worker detecta el OOM y marca el job como `failed`.

### 5.2 Recovery

- **`failure_reason`**: `'OOM'`.
- **Reintento**: el job se reintenta (hasta `max_attempts`).
- **Si se repite**: el job se marca como `failed` permanentemente.

## 6. Notas

- **No-root**: el contenedor se ejecuta como usuario no-root.
- **Read-only filesystem**: el filesystem es read-only (excepto `/tmp`).
- **Cgroup**: límites de CPU, memoria, PIDs.
- **Seccomp**: bloquear syscalls peligrosos.
- **Network egress**: solo acceso al LLM local.
- **Timeout**: 300 segundos por job.
- **OOM**: si se excede el límite de memoria, el proceso se mata.
