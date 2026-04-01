#!/usr/bin/env python3
"""
Simple Flask backend for Docker container management.
Provides REST API endpoints for restarting and recreating containers.
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import subprocess
import logging
import os
import json
import uuid
import threading
import sqlite3
import time
import shutil
import glob
import re
from datetime import datetime
import requests
from croniter import croniter

app = Flask(__name__, static_folder='static')
CORS(app)  # Enable CORS for frontend requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Container mappings: service_id -> {container_name, compose_dir, service (compose service name)}
CONTAINERS = {
    # Media
    'immich': {'name': 'immich', 'service': 'immich', 'compose_dir': 'immich'},
    'jellyfin': {'name': 'jellyfin', 'service': 'jellyfin', 'compose_dir': 'jellyfin'},
    'audiobookshelf': {'name': 'audiobookshelf', 'service': 'audiobookshelf', 'compose_dir': 'audiobookshelf'},
    'romm': {'name': 'romm', 'service': 'romm', 'compose_dir': 'romm'},

    # Downloads
    'qbittorrent': {'name': 'qbittorrent', 'service': 'qbittorrent', 'compose_dir': 'torrents'},
    'jackett': {'name': 'jackett', 'service': 'jackett', 'compose_dir': 'jackett'},
    'ytdlp': {'name': 'yt-dlp-web', 'service': 'yt-dlp-web', 'compose_dir': 'youtube-downloader'},
    'deemix': {'name': 'deemix', 'service': 'deemix', 'compose_dir': 'deemix'},

    # Forge Apps
    'lifeforge': {'name': 'lifeforge_app', 'service': 'lifeforge', 'compose_dir': '/home/brandon/projects/LifeForge'},
    'artforge': {'name': 'artforge', 'service': 'artforge', 'compose_dir': '/home/brandon/projects/ArtForge'},
    'wordforge': {'name': 'wordforge', 'service': 'wordforge', 'compose_dir': '/home/brandon/projects/WordForge'},
    'codeforge': {'name': 'codeforge_app', 'service': 'codeforge', 'compose_dir': '/home/brandon/projects/CodeForge'},

    # Reading
    'greatreads-prod': {'name': 'greatreads_app', 'service': 'greatreads', 'compose_dir': '/home/brandon/projects/GreatReads'},
    'booknews': {'name': 'booknews', 'service': 'booknews', 'compose_dir': '/home/brandon/projects/NerdNews'},
    'kidmedia': {'name': 'kidmedia', 'service': 'kidmedia', 'compose_dir': '/home/brandon/projects/KidMedia'},
    'calibre': {'name': 'calibre', 'service': 'calibre', 'compose_dir': 'calibre'},
    'libby-web': {'name': 'libby-web', 'service': 'libby-web', 'compose_dir': 'libby-web'},

    # Tools
    'stash': {'name': 'stash', 'service': 'stash', 'compose_dir': 'stash'},
    'trilium': {'name': 'trilium', 'service': 'trilium', 'compose_dir': 'trilium'},
    'dictionary': {'name': 'dictionary-api', 'service': 'dictionary-api', 'compose_dir': 'dictionary'},
    'vaultwarden': {'name': 'vaultwarden', 'service': 'vaultwarden', 'compose_dir': 'vaultwarden'},
}

# =============================================================================
# Infrastructure Monitoring — runs in a background thread every 60 s,
# persists to SQLite, caches latest snapshot for fast API responses.
# =============================================================================

DB_PATH = '/app/data/metrics.db'

# Every container we want to track on the health page (actual docker name → display info)
MONITORED_CONTAINERS = [
    {'name': 'booknews',       'label': 'NerdNews',       'category': 'Apps'},
    {'name': 'greatreads_app', 'label': 'GreatReads',     'category': 'Apps'},
    {'name': 'audiobookshelf', 'label': 'Audiobookshelf', 'category': 'Apps'},
    {'name': 'calibre',        'label': 'Calibre',        'category': 'Apps'},
    {'name': 'libby-web',      'label': 'Libby Browser',  'category': 'Apps'},
    {'name': 'lifeforge_app',  'label': 'LifeForge',      'category': 'Apps'},
    {'name': 'artforge',       'label': 'ArtForge',       'category': 'Apps'},
    {'name': 'wordforge',      'label': 'WordForge',      'category': 'Apps'},
    {'name': 'codeforge_app',  'label': 'CodeForge',      'category': 'Apps'},
    {'name': 'kidmedia',       'label': 'KidMedia',       'category': 'Apps'},
    {'name': 'immich',         'label': 'Immich',         'category': 'Media'},
    {'name': 'immich-db',      'label': 'Immich DB',      'category': 'Media'},
    {'name': 'jellyfin',       'label': 'Jellyfin',       'category': 'Media'},
    {'name': 'romm',           'label': 'RomM',           'category': 'Media'},
    {'name': 'romm-db',        'label': 'RomM DB',        'category': 'Media'},
    {'name': 'qbittorrent',    'label': 'qBittorrent',    'category': 'Downloads'},
    {'name': 'jackett',        'label': 'Jackett',        'category': 'Downloads'},
    {'name': 'flaresolverr',   'label': 'FlareSolverr',   'category': 'Downloads'},
    {'name': 'yt-dlp-web',     'label': 'YT-DLP',         'category': 'Downloads'},
    {'name': 'deemix',         'label': 'Deemix',         'category': 'Downloads'},
    {'name': 'trilium',        'label': 'Trilium',        'category': 'Tools'},
    {'name': 'stash',          'label': 'Stash',          'category': 'Tools'},
    {'name': 'dictionary-api', 'label': 'Dictionary',     'category': 'Tools'},
    {'name': 'vaultwarden',    'label': 'Vaultwarden',    'category': 'Tools'},
    {'name': 'fileshare-miniserve',   'label': 'Fileshare (serve)',  'category': 'Tools', 'optional': True},
    {'name': 'fileshare-cloudflared', 'label': 'Fileshare (tunnel)', 'category': 'Tools', 'optional': True},
    {'name': 'mullvad-vpn',    'label': 'Mullvad VPN',    'category': 'Infrastructure'},
    {'name': 'dashboard',      'label': 'Dashboard',      'category': 'Infrastructure'},
]

THRESHOLDS = {
    'cpu':         {'warn': 85, 'crit': 95},
    'ram':         {'warn': 85, 'crit': 95},
    'swap':        {'warn': 50, 'crit': 75},
    'docker_disk': {'warn': 75, 'crit': 85},
    'ssd250_disk': {'warn': 85, 'crit': 93},
    'nas_disk':    {'warn': 85, 'crit': 93},
    'backups_disk': {'warn': 85, 'crit': 93},
    'external_disk': {'warn': 85, 'crit': 93},
    'nvme_disk': {'warn': 85, 'crit': 93},
    'allston_disk': {'warn': 85, 'crit': 93},
    'flash_disk': {'warn': 90, 'crit': 98},
}

DRIVE_LAYOUT = [
    {
        'id': 'nvme_disk',
        'name': 'nvme',
        'device': 'nvme0n1',
        'category': 'internal',
        'mountpoint': '/',
        'size_gb_hint': 233,
        'purpose': 'Proxmox OS, VM disks, swap',
    },
    {
        'id': 'nas_disk',
        'name': 'boston',
        'device': 'sda',
        'category': 'internal',
        'mountpoint': '/mnt/boston',
        'size_gb_hint': 7300,
        'purpose': 'VM backups, bulk storage',
    },
    {
        'id': 'ssd250_disk',
        'name': 'ssd250',
        'device': 'sdb',
        'category': 'internal',
        'mountpoint': '/mnt/ssd250',
        'size_gb_hint': 224,
        'purpose': 'Extra VM storage',
    },
    {
        'id': 'backups_disk',
        'name': 'backups',
        'device': 'sdc',
        'category': 'internal',
        'mountpoint': '/mnt/backups',
        'size_gb_hint': 932,
        'purpose': 'Local file backups',
    },
    {
        'id': 'allston_disk',
        'name': 'allston',
        'device': 'sdd',
        'category': 'external',
        'mountpoint': '/mnt/allston',
        'size_gb_hint': 1800,
        'purpose': 'Proxmox ISO/image storage',
    },
    {
        'id': 'external_disk',
        'name': 'external',
        'device': 'sdf',
        'category': 'external',
        'mountpoint': '/mnt/external',
        'size_gb_hint': 1800,
        'purpose': 'Personal files and media',
    },
    {
        'id': 'flash_disk',
        'name': 'flash drive',
        'device': 'sde',
        'category': 'external',
        'mountpoint': '/mnt/flash',
        'size_gb_hint': 14,
        'purpose': 'Temporary portable storage (ext4, label: flash-drive)',
    },
]

PROJECTS_ROOT = '/home/brandon/projects'

AUTOMATION_CONTAINERS = [
    'dashboard', 'libby-web', 'mullvad-vpn'
]

BACKUP_JOB_DEFS = [
    {
        'id': 'internal_hourly',
        'title': 'Hourly internal backup',
        'script': 'backup-script.sh',
        'schedule_hint': '0 * * * *',
        'source_root': '/mnt/boston',
        'dest_root': '/mnt/backups',
        'paths': [
            'docker-backups',
            'documents',
            'media/audiobooks',
            'media/books',
            'media/games',
            'media/audiobookshelf',
            'media/music',
            'media/other',
        ],
        'expected_steps': 8,
    },
    {
        'id': 'external_hourly',
        'title': 'Hourly external media backup',
        'script': 'backup-external.sh',
        'schedule_hint': '5 * * * *',
        'source_root': '/mnt/boston',
        'dest_root': '/mnt/external',
        'paths': [
            'media/pictures',
            'media/videos',
        ],
        'expected_steps': 2,
    },
]

_latest_status: dict = {}
_status_lock = threading.Lock()
_latest_extended: dict = {}
_extended_lock = threading.Lock()


def _build_proxmox_ssh_base(user_env: str = 'PROXMOX_SSH_USER',
                            password_env: str = 'PROXMOX_SSH_PASSWORD',
                            default_user: str = 'brandon') -> tuple[list[str] | None, str | None]:
    """Build SSH command prefix from environment variables."""
    host = os.environ.get('PROXMOX_SSH_HOST', '').strip()
    user = os.environ.get(user_env, default_user).strip()
    password = os.environ.get(password_env, '').strip()
    if password.startswith(('"', "'")) and password.endswith(('"', "'")) and len(password) >= 2:
        password = password[1:-1]
    password = password.replace('\\#', '#')

    if not host:
        return None, 'PROXMOX_SSH_HOST not configured'

    use_password = bool(password and shutil.which('sshpass'))
    ssh_base = [
        'ssh',
        '-o', f'BatchMode={"no" if use_password else "yes"}',
        '-o', 'PreferredAuthentications=password,publickey',
        '-o', 'ConnectTimeout=6',
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'UserKnownHostsFile=/dev/null',
        f'{user}@{host}',
    ]
    if use_password:
        ssh_base = ['sshpass', '-p', password] + ssh_base
    return ssh_base, None


def _init_db():
    os.makedirs('/app/data', exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript('''
        CREATE TABLE IF NOT EXISTS metrics (
            ts              INTEGER PRIMARY KEY,
            cpu_pct         REAL,
            ram_used_mb     INTEGER,
            ram_total_mb    INTEGER,
            swap_used_mb    INTEGER,
            swap_total_mb   INTEGER,
            docker_disk_pct INTEGER,
            nas_disk_pct    INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_m_ts ON metrics(ts);
        CREATE TABLE IF NOT EXISTS container_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              INTEGER,
            container_name  TEXT,
            status          TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ce_ts  ON container_events(ts);
        CREATE INDEX IF NOT EXISTS idx_ce_con ON container_events(container_name, ts);
    ''')
    con.commit()
    con.close()


def _read_cpu() -> float:
    """Return host CPU usage % by sampling /proc/stat twice 1 s apart."""
    def _stat():
        with open('/proc/stat') as f:
            v = list(map(int, f.readline().split()[1:]))
        return v[3] + v[4], sum(v)   # (idle+iowait, total)
    i1, t1 = _stat()
    time.sleep(1)
    i2, t2 = _stat()
    dt = t2 - t1
    return round((1 - (i2 - i1) / dt) * 100, 1) if dt else 0.0


def _read_mem() -> dict:
    """Parse /proc/meminfo for RAM and swap figures."""
    kv: dict = {}
    with open('/proc/meminfo') as f:
        for line in f:
            k, v = line.split(':')
            kv[k.strip()] = int(v.split()[0])   # values in kB
    return {
        'ram_used_mb':  (kv['MemTotal'] - kv['MemAvailable']) // 1024,
        'ram_total_mb':  kv['MemTotal']  // 1024,
        'swap_used_mb':  (kv['SwapTotal'] - kv['SwapFree']) // 1024,
        'swap_total_mb': kv['SwapTotal'] // 1024,
    }


def _read_disk(path: str) -> dict:
    try:
        st = os.statvfs(path)
        total = st.f_blocks * st.f_frsize
        avail = st.f_bavail * st.f_frsize
        used  = total - avail
        pct   = int(used / total * 100) if total else 0
        return {'used_gb': round(used / 1e9, 1), 'total_gb': round(total / 1e9, 1), 'pct': pct}
    except Exception:
        return {'used_gb': 0, 'total_gb': 0, 'pct': 0}


def _read_proxmox_disks_remote() -> dict[str, dict]:
    """Read selected Proxmox mount usage over SSH as a fallback for host-mismatch setups."""
    ssh_base, err = _build_proxmox_ssh_base()
    if not ssh_base or err:
        return {}

    code, out, _ = _run_cmd(
        ssh_base + [
            "df -B1 --output=target,size,used,pcent /mnt/backups /mnt/external /mnt/ssd250 2>/dev/null | tail -n +2"
        ],
        timeout=12,
    )
    if code != 0 or not out:
        return {}

    mapping = {
        '/mnt/backups': 'backups_disk',
        '/mnt/external': 'external_disk',
        '/mnt/ssd250': 'ssd250_disk',
    }
    result: dict[str, dict] = {}
    for ln in out.splitlines():
        parts = ln.split()
        if len(parts) < 4:
            continue
        target, size_b, used_b, pct_s = parts[:4]
        key = mapping.get(target)
        if not key:
            continue
        try:
            size = int(size_b)
            used = int(used_b)
            pct = int(str(pct_s).rstrip('%'))
        except Exception:
            continue
        result[key] = {
            'used_gb': round(used / 1e9, 1),
            'total_gb': round(size / 1e9, 1),
            'pct': pct,
        }
    return result


def _read_drive_inventory_remote() -> list[dict]:
    """Return full 7-drive inventory with mount status and usage from Proxmox when available."""
    ssh_base, _ = _build_proxmox_ssh_base()
    if not ssh_base:
        out = []
        for d in DRIVE_LAYOUT:
            out.append({
                **d,
                'mounted': False if d.get('mountpoint') else None,
                'used_gb': 0,
                'total_gb': d.get('size_gb_hint', 0),
                'pct': 0,
                'severity': 'warn',
                'source': 'hint',
            })
        return out

    df_cmd = "df -B1 --output=target,size,used,pcent / /mnt/boston /mnt/backups /mnt/external /mnt/ssd250 /mnt/allston /mnt/flash 2>/dev/null | tail -n +2"
    c_df, out_df, _ = _run_cmd(ssh_base + [df_cmd], timeout=12)
    by_mount: dict[str, dict] = {}
    if c_df == 0 and out_df:
        for ln in out_df.splitlines():
            p = ln.split()
            if len(p) < 4:
                continue
            try:
                target = p[0]
                size = int(p[1])
                used = int(p[2])
                pct = int(p[3].rstrip('%'))
            except Exception:
                continue
            by_mount[target] = {
                'used_gb': round(used / 1e9, 1),
                'total_gb': round(size / 1e9, 1),
                'pct': pct,
            }

    lsblk_cmd = "lsblk -b -P -o NAME,SIZE,TYPE,MOUNTPOINT,RM,MODEL 2>/dev/null"
    c_lb, out_lb, _ = _run_cmd(ssh_base + [lsblk_cmd], timeout=12)
    by_device: dict[str, dict] = {}
    if c_lb == 0 and out_lb:
        for ln in out_lb.splitlines():
            kv = dict(re.findall(r'(\w+)="([^"]*)"', ln))
            name = kv.get('NAME')
            typ = kv.get('TYPE')
            if not name or typ != 'disk':
                continue
            try:
                size = int(kv.get('SIZE', '0'))
            except Exception:
                size = 0
            by_device[name] = {
                'size_gb': round(size / 1e9, 1),
                'model': kv.get('MODEL') or None,
                'rm': kv.get('RM') == '1',
            }

    out: list[dict] = []
    for d in DRIVE_LAYOUT:
        mount = d.get('mountpoint')
        m = by_mount.get(mount) if mount else None
        dev = by_device.get(d['device'])
        total_gb = (m or {}).get('total_gb', dev.get('size_gb') if dev else d.get('size_gb_hint', 0))
        used_gb = (m or {}).get('used_gb', 0)
        pct = (m or {}).get('pct', 0)

        if m:
            sev = _sev(pct, d['id']) if d['id'] in THRESHOLDS else ('crit' if pct >= 93 else 'warn' if pct >= 85 else 'ok')
            mounted = True
            source = 'df'
        else:
            mounted = False if mount else None
            if dev:
                sev = 'warn' if mount else 'ok'
                source = 'lsblk'
            else:
                sev = 'warn'
                source = 'hint'

        out.append({
            **d,
            'model': (dev or {}).get('model'),
            'removable': (dev or {}).get('rm'),
            'mounted': mounted,
            'used_gb': used_gb,
            'total_gb': total_gb,
            'pct': pct,
            'severity': sev,
            'source': source,
        })
    return out


def _read_containers() -> list:
    """Get status of every monitored container in a single docker ps call."""
    try:
        r = subprocess.run(
            ['docker', 'ps', '-a', '--format', '{{.Names}}|{{.Status}}'],
            capture_output=True, text=True, timeout=15)
        live = {}
        for line in r.stdout.strip().splitlines():
            if '|' in line:
                n, s = line.split('|', 1)
                live[n.strip()] = s.strip()
    except Exception:
        live = {}

    out = []
    for c in MONITORED_CONTAINERS:
        raw = live.get(c['name'], '')
        if not raw:
            if c.get('optional'):
                state, health = 'idle', None
            else:
                state, health = 'missing', None
        elif raw.lower().startswith('up'):
            state = 'running'
            health = ('unhealthy' if '(unhealthy)' in raw else
                      'healthy'   if '(healthy)'   in raw else
                      'starting'  if '(starting)'  in raw else None)
        else:
            state, health = 'stopped', None
        out.append({**c, 'state': state, 'health': health, 'raw_status': raw})
    return out


def _sev(value: float, key: str) -> str:
    t = THRESHOLDS.get(key, {})
    return ('crit' if value >= t.get('crit', 101) else
            'warn' if value >= t.get('warn', 101) else 'ok')


def _read_container_stats() -> list:
    """Per-container CPU % and memory usage via a single docker stats call."""
    try:
        r = subprocess.run(
            ['docker', 'stats', '--no-stream', '--format',
             '{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}}'],
            capture_output=True, text=True, timeout=30)
        out = []
        for line in r.stdout.strip().splitlines():
            parts = line.split(',', 3)
            if len(parts) < 4:
                continue
            name, cpu_s, mem_s, memp_s = parts
            try:
                cpu_pct  = float(cpu_s.strip().rstrip('%') or 0)
                mem_pct  = float(memp_s.strip().rstrip('%') or 0)
                mem_used = mem_s.split('/')[0].strip()
            except ValueError:
                continue
            out.append({'name': name.strip(), 'cpu_pct': round(cpu_pct, 2),
                        'mem_pct': round(mem_pct, 2), 'mem_used': mem_used})
        # Sort by CPU descending so the frontend can just slice [:N]
        out.sort(key=lambda x: x['cpu_pct'], reverse=True)
        return out
    except Exception as ex:
        logger.warning(f'docker stats error: {ex}')
        return []


def _run_cmd(cmd: list, timeout: int = 15, cwd: str | None = None) -> tuple[int, str, str]:
    """Run a command and return (exit_code, stdout, stderr) without raising."""
    try:
        res = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return res.returncode, (res.stdout or '').strip(), (res.stderr or '').strip()
    except Exception as ex:
        return 1, '', str(ex)


def _repo_status(repo: dict) -> dict:
    name = repo['name']
    path = repo['path']

    def git(args: list[str]) -> tuple[int, str, str]:
        return _run_cmd(['git', '-c', f'safe.directory={path}', '-C', path] + args)

    if not os.path.isdir(path):
        return {
            'name': name,
            'path': path,
            'severity': 'crit',
            'state': 'missing',
            'branch': None,
            'dirty_files': 0,
            'conflicts': 0,
            'summary': 'Repository path not found',
        }

    code, out, err = git(['rev-parse', '--is-inside-work-tree'])
    if code != 0 or out.lower() != 'true':
        if 'dubious ownership' in (err or '').lower():
            return {
                'name': name,
                'path': path,
                'severity': 'warn',
                'state': 'safe_directory_required',
                'branch': None,
                'dirty_files': 0,
                'conflicts': 0,
                'summary': 'Git safe.directory ownership check blocked this repo',
            }
        return {
            'name': name,
            'path': path,
            'severity': 'crit',
            'state': 'not_git',
            'branch': None,
            'dirty_files': 0,
            'conflicts': 0,
            'summary': 'Not a git repository',
        }

    _, branch, _ = git(['branch', '--show-current'])
    _, porcelain, _ = git(['status', '--porcelain'])

    lines = [ln for ln in porcelain.splitlines() if ln.strip()]
    conflict_prefixes = {'UU', 'AA', 'DD', 'AU', 'UA', 'DU', 'UD'}
    conflicts = 0
    for ln in lines:
        p = ln[:2].strip()
        if p in conflict_prefixes:
            conflicts += 1

    dirty_files = len(lines)
    dirty_non_conflict = max(dirty_files - conflicts, 0)

    upstream = None
    ahead = 0
    behind = 0
    up_code, up_out, _ = git(['rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}'])
    if up_code == 0 and up_out:
        upstream = up_out
        lr_code, lr_out, _ = git(['rev-list', '--left-right', '--count', '@{upstream}...HEAD'])
        if lr_code == 0 and lr_out:
            try:
                left, right = lr_out.split()
                behind = int(left)
                ahead = int(right)
            except Exception:
                ahead, behind = 0, 0

    if conflicts > 0:
        severity = 'crit'
        state = 'merge_conflict'
        summary = f'{conflicts} merge conflict file(s)'
    elif dirty_non_conflict > 0:
        severity = 'warn'
        state = 'dirty'
        summary = f'{dirty_non_conflict} uncommitted change(s)'
    elif behind > 0 and ahead > 0:
        severity = 'warn'
        state = 'diverged'
        summary = f'Diverged from upstream (+{ahead}/-{behind})'
    elif behind > 0:
        severity = 'warn'
        state = 'behind'
        summary = f'Behind upstream by {behind} commit(s)'
    elif ahead > 0:
        severity = 'warn'
        state = 'ahead'
        summary = f'Ahead of upstream by {ahead} commit(s)'
    elif upstream is None:
        severity = 'warn'
        state = 'no_upstream'
        summary = 'No upstream tracking branch configured'
    else:
        severity = 'ok'
        state = 'clean'
        summary = 'Clean and up to date with upstream refs'

    return {
        'name': name,
        'path': path,
        'severity': severity,
        'state': state,
        'branch': branch or None,
        'upstream': upstream,
        'dirty_files': dirty_files,
        'conflicts': conflicts,
        'summary': summary,
    }


def _discover_repo_targets() -> list[dict]:
    repos: list[dict] = []
    try:
        if not os.path.isdir(PROJECTS_ROOT):
            return repos
        for entry in os.scandir(PROJECTS_ROOT):
            if not entry.is_dir(follow_symlinks=False):
                continue
            if os.path.isdir(os.path.join(entry.path, '.git')):
                repos.append({'name': entry.name, 'path': entry.path})
    except Exception:
        return repos
    repos.sort(key=lambda r: r['name'].lower())
    return repos


def _read_git_repos() -> dict:
    targets = _discover_repo_targets()
    repos = [_repo_status(r) for r in targets]
    worst = 'ok'
    if any(r['severity'] == 'crit' for r in repos):
        worst = 'crit'
    elif any(r['severity'] == 'warn' for r in repos):
        worst = 'warn'
    return {
        'severity': worst,
        'repos': repos,
    }


def _parse_cron_line(line: str) -> tuple[str, str] | None:
    s = line.strip()
    if not s or s.startswith('#'):
        return None
    parts = s.split()
    if len(parts) < 6:
        return None
    schedule = ' '.join(parts[:5])
    command = ' '.join(parts[5:])
    return schedule, command


def _extract_log_time(log_line: str) -> str | None:
    # Supports ISO-leading log lines and syslog-style month/day lines.
    m = re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)?)', log_line)
    if m:
        return m.group(1)
    m = re.match(r'^([A-Z][a-z]{2}\s+\d+\s+\d{2}:\d{2}:\d{2})', log_line)
    if m:
        return m.group(1)
    return None


def _find_last_cron_run(command: str) -> dict | None:
    """Best-effort lookup in syslog/cron logs for the command basename."""
    cmd_token = command.strip().split()[0] if command.strip() else ''
    base = os.path.basename(cmd_token)
    if not base:
        return None

    log_candidates = [
        '/host_var_log/syslog', '/host_var_log/cron.log',
        '/var/log/syslog', '/var/log/cron.log',
    ]
    for log_path in log_candidates:
        if not os.path.exists(log_path):
            continue
        code, out, _ = _run_cmd([
            'sh', '-c',
            f"tail -n 8000 {log_path} | grep -i 'CRON' | grep -F '{base}' | tail -n 1"
        ], timeout=8)
        if code == 0 and out:
            return {
                'line': out,
                'time': _extract_log_time(out),
                'log_path': log_path,
            }
    return None


def _read_backup_log_status_local(script_name: str) -> dict | None:
    """Best-effort status from local backup log files."""
    patterns = {
        'backup-script.sh': os.path.expanduser('~/.local/state/backups/backup-20*.log'),
        'backup-external.sh': os.path.expanduser('~/.local/state/backups/backup-external-*.log'),
    }
    pattern = patterns.get(script_name)
    if not pattern:
        return None

    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if not files:
        return None

    latest = files[0]
    try:
        with open(latest, 'r', errors='replace') as f:
            tail = f.readlines()[-120:]
        content = ''.join(tail)
        completed = 'completed at' in content.lower()
        skipped = 'skipping external backup' in content.lower()
        failed = 'FAILED' in content
        mtime = datetime.fromtimestamp(os.path.getmtime(latest)).isoformat(timespec='seconds')
        if failed:
            severity, note = 'crit', 'Backup log reports one or more failed sections.'
        elif skipped:
            severity, note = 'warn', 'External backup was skipped because drive was not mounted.'
        elif completed:
            severity, note = 'ok', 'Backup completed successfully.'
        else:
            severity, note = 'warn', 'Backup log found but completion status is unclear.'
        return {
            'time': mtime,
            'log_path': latest,
            'severity': severity,
            'status_note': note,
        }
    except Exception:
        return None


def _cron_description(command: str) -> str:
    c = command.lower()
    if '>> /home/brandon/projects/docker/backup.log 2>&1' in c:
        return 'Docker Log Backups'
    if '>> /home/brandon/backups/immich-daily/cron.log 2>&1' in c:
        return 'Immich Log Backups'
    if '/home/brandon/projects/docker/immich/watchdog.sh' in c:
        return 'Immich Watchdog'
    if 'backup-script.sh' in c:
        return 'Hourly backup to internal backup storage (documents/media/dockerhost).'
    if 'backup-external.sh' in c:
        return 'Hourly backup to external drive when connected (pictures/videos).'
    if 'run-parts --report /etc/cron.hourly' in c:
        return 'Runs all hourly system maintenance jobs.'
    if 'run-parts --report /etc/cron.daily' in c:
        return 'Runs all daily system maintenance jobs.'
    if 'run-parts --report /etc/cron.weekly' in c:
        return 'Runs all weekly system maintenance jobs.'
    if 'run-parts --report /etc/cron.monthly' in c:
        return 'Runs all monthly system maintenance jobs.'
    if 'docker' in c and 'compose' in c:
        return 'Docker automation task.'
    if '/home/brandon/projects/' in c:
        try:
            script = os.path.basename(command.split()[0])
            return f'Runs script: {script}'
        except Exception:
            pass
    return 'Scheduled task.'


def _cron_schedule_human(schedule: str) -> str:
    parts = schedule.split()
    if len(parts) != 5:
        return f'Custom schedule ({schedule})'
    minute, hour, dom, month, dow = parts
    if schedule == '* * * * *':
        return 'Every minute'
    if minute.startswith('*/') and minute[2:].isdigit() and hour == '*' and dom == '*' and month == '*' and dow == '*':
        return f'Every {int(minute[2:])} minutes'
    if hour.startswith('*/') and hour[2:].isdigit() and dom == '*' and month == '*' and dow == '*' and minute.isdigit():
        return f'Every {int(hour[2:])} hours at minute {int(minute):02d}'
    if hour == '*' and dom == '*' and month == '*' and dow == '*' and minute.isdigit():
        return f'Hourly at minute {int(minute):02d}'
    if dom == '*' and month == '*' and dow == '*' and hour.isdigit() and minute.isdigit():
        return f'Daily at {int(hour):02d}:{int(minute):02d}'
    if dom == '*' and month == '*' and dow in {'0', '7', '1', '2', '3', '4', '5', '6'} and hour.isdigit() and minute.isdigit():
        days = {'0': 'Sunday', '7': 'Sunday', '1': 'Monday', '2': 'Tuesday', '3': 'Wednesday', '4': 'Thursday', '5': 'Friday', '6': 'Saturday'}
        return f"Weekly on {days[dow]} at {int(hour):02d}:{int(minute):02d}"
    if dom.isdigit() and month == '*' and dow == '*' and hour.isdigit() and minute.isdigit():
        return f'Monthly on day {int(dom)} at {int(hour):02d}:{int(minute):02d}'
    return f'Custom cron ({schedule})'


def _cron_next_run(schedule: str) -> str | None:
    try:
        nxt = croniter(schedule, datetime.now()).get_next(datetime)
        return nxt.isoformat(timespec='seconds')
    except Exception:
        return None


def _is_noisy_noop_cron(command: str) -> bool:
    c = (command or '').strip().lower()
    if '/dev/null' not in c:
        return False
    if c in ('>/dev/null 2>&1', '> /dev/null 2>&1', '>>/dev/null 2>&1', '>> /dev/null 2>&1'):
        return True
    if c.startswith('command -v ') and '> /dev/null &&' in c:
        return True
    noisy_prefixes = (
        'test -x /usr/sbin/anacron',
        '[ -x /usr/lib/php/sessionclean ]',
    )
    if c.startswith(noisy_prefixes):
        return True
    if 'run-parts --report /etc/cron.' in c:
        return True
    return False


def _normalized_cron_entry(source: str, schedule: str, command: str) -> dict | None:
    if _is_noisy_noop_cron(command):
        return None
    cmd_token = command.split()[0] if command else ''
    script_exists = bool(cmd_token and cmd_token.startswith('/') and os.path.exists(cmd_token))
    sev = 'ok' if (not cmd_token.startswith('/') or script_exists) else 'crit'
    cmd_base = os.path.basename((command.strip().split()[0] if command.strip() else ''))
    last = _find_last_cron_run(command) or {}
    if not last and cmd_base in ('backup-script.sh', 'backup-external.sh'):
        last = _read_backup_log_status_local(cmd_base) or {}

    status_note = last.get('status_note')
    if last.get('time') is None and sev != 'crit':
        sev = 'warn'
    return {
        'source': source,
        'schedule': schedule,
        'schedule_human': _cron_schedule_human(schedule),
        'command': command,
        'description': _cron_description(command),
        'next_run': _cron_next_run(schedule),
        'script_exists': script_exists if cmd_token.startswith('/') else None,
        'last_seen': last.get('time'),
        'last_seen_raw': last.get('line'),
        'log_path': last.get('log_path'),
        'status_note': status_note,
        'severity': sev,
    }


def _read_backup_log_status_remote(ssh_base: list[str], script_name: str) -> dict | None:
    """Best-effort status from backup logs on the Proxmox host for brandon-run scripts."""
    patterns = {
        'backup-script.sh': 'backup-20*.log',
        'backup-external.sh': 'backup-external-*.log',
    }
    pattern = patterns.get(script_name)
    if not pattern:
        return None

    cmd = (
        "LOG_DIR=\"${HOME}/.local/state/backups\"; "
        f"LATEST=$(ls -1t \"$LOG_DIR\"/{pattern} 2>/dev/null | head -n 1); "
        "if [ -z \"$LATEST\" ]; then exit 3; fi; "
        "echo \"PATH:$LATEST\"; "
        "date -r \"$LATEST\" --iso-8601=seconds | sed 's/^/MTIME:/' ; "
        "tail -n 120 \"$LATEST\""
    )
    code, out, _ = _run_cmd(ssh_base + [cmd], timeout=12)
    if code != 0 or not out:
        return None

    log_path = None
    mtime = None
    for ln in out.splitlines():
        if ln.startswith('PATH:'):
            log_path = ln.split(':', 1)[1].strip()
        elif ln.startswith('MTIME:'):
            mtime = ln.split(':', 1)[1].strip()

    content = out
    completed = 'completed at' in content.lower()
    skipped = 'skipping external backup' in content.lower()
    failed = 'FAILED' in content
    if failed:
        severity, note = 'crit', 'Backup log reports one or more failed sections.'
    elif skipped:
        severity, note = 'warn', 'External backup was skipped because drive was not mounted.'
    elif completed:
        severity, note = 'ok', 'Backup completed successfully.'
    else:
        severity, note = 'warn', 'Backup log found but completion status is unclear.'

    return {
        'time': mtime,
        'log_path': log_path,
        'severity': severity,
        'status_note': note,
    }


def _backup_sync_state(entry: dict | None, running: bool, expected_steps: int, success_count: int | None) -> str:
    if running:
        return 'running'
    note = ((entry or {}).get('status_note') or '').lower()
    if 'skipped external backup' in note:
        return 'skipped'
    if (entry or {}).get('severity') == 'crit':
        return 'mismatch'
    if success_count is not None and expected_steps > 0 and success_count >= expected_steps:
        return 'matched'
    if 'completed successfully' in note:
        return 'matched'
    if (entry or {}).get('last_seen'):
        return 'unknown'
    return 'unknown'


def _running_backup_progress(ssh_base: list[str] | None, script_name: str, expected_steps: int, log_path: str | None) -> dict:
    """Return running flag and best-effort progress for backup scripts."""
    running = False
    success_count = None
    progress_pct = None

    if ssh_base:
        code, out, _ = _run_cmd(ssh_base + [f"pgrep -af {script_name} | grep -v grep"], timeout=8)
        running = bool(code == 0 and out.strip())

    if ssh_base and log_path:
        code, content, _ = _run_cmd(ssh_base + [f"tail -n 260 '{log_path}' 2>/dev/null"], timeout=8)
        if code == 0 and content:
            success_count = len(re.findall(r'SUCCESS:\s+Backed up:', content))
            markers = re.findall(r'---\s+Backup\s+(\d+)/(\d+):', content)
            current_idx = 0
            total = expected_steps
            if markers:
                try:
                    current_idx = max(int(m[0]) for m in markers)
                    total = int(markers[-1][1]) if int(markers[-1][1]) > 0 else expected_steps
                except Exception:
                    current_idx = 0
                    total = expected_steps

            if running:
                done = max(success_count or 0, max(current_idx - 1, 0))
                progress_pct = int(min(99, (done / max(total, 1)) * 100))
            elif success_count is not None and expected_steps > 0:
                progress_pct = int(min(100, (success_count / expected_steps) * 100))

    return {
        'running': running,
        'progress_pct': progress_pct,
        'success_count': success_count,
    }


def _read_vm_backup_overview() -> dict:
    """Best-effort Proxmox VM backup visibility."""
    root_base, _ = _build_proxmox_ssh_base('PROXMOX_ROOT_SSH_USER', 'PROXMOX_ROOT_SSH_PASSWORD', 'root')
    user_base, _ = _build_proxmox_ssh_base()
    ssh_candidates = [b for b in [root_base, user_base] if b]

    if not ssh_candidates:
        return {
            'id': 'proxmox_vm',
            'title': 'Proxmox backup job: boston_backups',
            'includes': [
                'Location: /mnt/boston/proxmox-backups',
                'Scope: VMs 101, 100, 102, 103',
                'Format: vzdump compressed VMA archive',
                'Retention: keep-weekly=3',
            ],
            'schedule': None,
            'next_run': None,
            'last_run': None,
            'running': False,
            'progress_pct': None,
            'sync_state': 'unknown',
            'severity': 'warn',
            'status_note': 'Proxmox SSH not configured for VM backup visibility.',
            'artifacts': [],
        }

    ssh_base = None
    files_cmd = "ls -1t /mnt/boston/proxmox-backups/dump/vzdump-* /mnt/boston/proxmox-backups/vzdump-* /mnt/backups/vzdump-* /var/lib/vz/dump/vzdump-* 2>/dev/null | head -n 24"
    code = 1
    out = ''
    for base in ssh_candidates:
        c, o, _ = _run_cmd(base + [files_cmd], timeout=12)
        if c == 0:
            code, out = c, o
            ssh_base = base
            break
    if ssh_base is None:
        ssh_base = ssh_candidates[0]

    artifacts = [ln.strip() for ln in out.splitlines() if ln.strip()] if code == 0 else []

    last_run = None
    if artifacts:
        c2, ts, _ = _run_cmd(ssh_base + [f"date -r '{artifacts[0]}' --iso-8601=seconds"], timeout=8)
        if c2 == 0 and ts:
            last_run = ts.strip()

    running = False
    c3, p_out, _ = _run_cmd(ssh_base + ["pgrep -af 'vzdump|proxmox-backup-client' | grep -v grep"], timeout=8)
    if c3 == 0 and p_out.strip():
        running = True

    schedule = None
    c4, s_out, _ = _run_cmd(ssh_base + ["awk '/^schedule[[:space:]]/{print; exit}' /etc/pve/vzdump.cron 2>/dev/null"], timeout=8)
    if c4 == 0 and s_out.strip():
        raw = s_out.strip()
        m = re.match(r'^schedule\s+([a-z]{3})\s+(\d{2}):(\d{2})$', raw)
        if m:
            dow, hh, mm = m.groups()
            days = {
                'sun': 'Sunday', 'mon': 'Monday', 'tue': 'Tuesday', 'wed': 'Wednesday',
                'thu': 'Thursday', 'fri': 'Friday', 'sat': 'Saturday',
            }
            schedule = f"Every {days.get(dow, dow)} at {hh}:{mm}"
        else:
            schedule = raw

    # If config parsing is unavailable from the current SSH user, fall back to known job cadence.
    if not schedule:
        schedule = 'Every Sunday at 03:00'

    next_run = _cron_next_run('0 3 * * 0')

    total_size = None
    c5, sz_out, _ = _run_cmd(ssh_base + ["du -sb /mnt/boston/proxmox-backups 2>/dev/null | awk '{print $1}'"], timeout=8)
    if c5 == 0 and sz_out.strip().isdigit():
        try:
            total_size = round(int(sz_out.strip()) / 1e9, 1)
        except Exception:
            total_size = None

    severity = 'ok' if artifacts else 'warn'
    if running:
        severity = 'warn'
    status_note = 'Detected VM backup archives.' if artifacts else 'No VM backup archives detected in expected paths.'
    if running:
        status_note = 'VM backup appears to be running now.'
    elif artifacts and total_size is not None:
        status_note = f'Detected VM backup archives (~{total_size} GB total).'

    return {
        'id': 'proxmox_vm',
        'title': 'Proxmox backup job: boston_backups',
        'includes': [
            'Location: /mnt/boston/proxmox-backups',
            'Scope: VMs 101, 100, 102, 103',
            'Format: vzdump compressed VMA archive',
            'Retention: keep-weekly=3',
            'VM 102 currently backs up EFI/TPM only (no main disk)',
        ],
        'schedule': schedule,
        'next_run': next_run,
        'last_run': last_run,
        'running': running,
        'progress_pct': 25 if running else None,
        'sync_state': 'matched' if artifacts else 'unknown',
        'severity': severity,
        'status_note': status_note,
        'artifacts': artifacts[:5],
    }


def _read_config_backup_overview(cron_entry: dict | None = None) -> dict:
    """Best-effort Proxmox config backup visibility."""
    user_base, _ = _build_proxmox_ssh_base()

    schedule = (cron_entry or {}).get('schedule') or '0 2 * * *'
    next_run = (cron_entry or {}).get('next_run') or _cron_next_run('0 2 * * *')

    base_info: dict = {
        'id': 'proxmox_config',
        'title': 'Daily Proxmox config backup',
        'includes': [
            '/etc/pve → /mnt/boston/proxmox-config-backups (Proxmox config: VMs, storage, network, users)',
            '/etc/network, /etc/fstab, /etc/hostname, /etc/hosts',
            '/etc/udev/rules.d (automount rules)',
            '/home/brandon (scripts, dotfiles)',
        ],
        'schedule': schedule,
        'next_run': next_run,
        'last_run': None,
        'running': False,
        'progress_pct': None,
        'sync_state': 'unknown',
        'severity': 'warn',
        'status_note': 'No config backup archives found.',
        'log_path': '/mnt/boston/proxmox-config-backups/',
    }

    if not user_base:
        base_info['status_note'] = 'Proxmox SSH not configured for config backup visibility.'
        return base_info

    archives_cmd = "ls -1t /mnt/boston/proxmox-config-backups/proxmox-config-*.tar.gz 2>/dev/null | head -5"
    c, out, _ = _run_cmd(user_base + [archives_cmd], timeout=12)
    artifacts = [ln.strip() for ln in out.splitlines() if ln.strip()] if c == 0 else []

    last_run = None
    if artifacts:
        c2, ts, _ = _run_cmd(user_base + [f"date -r '{artifacts[0]}' --iso-8601=seconds"], timeout=8)
        if c2 == 0 and ts:
            last_run = ts.strip()

    running = False
    c3, p_out, _ = _run_cmd(user_base + ["pgrep -af 'proxmox-config-backup.sh' | grep -v grep"], timeout=8)
    if c3 == 0 and p_out.strip():
        running = True

    total_size_gb = None
    if artifacts:
        c4, sz_out, _ = _run_cmd(user_base + ["du -sb /mnt/boston/proxmox-config-backups/ 2>/dev/null | awk '{print $1}'"], timeout=8)
        if c4 == 0 and sz_out.strip().isdigit():
            try:
                total_size_gb = round(int(sz_out.strip()) / 1e9, 1)
            except Exception:
                pass

    sync_state = 'unknown'
    severity = 'warn'
    if artifacts:
        sync_state = 'matched'
        severity = 'ok'
        c5, age_out, _ = _run_cmd(user_base + [f"echo $(( $(date +%s) - $(date -r '{artifacts[0]}' +%s) ))"], timeout=8)
        if c5 == 0 and age_out.strip().isdigit():
            age_hours = int(age_out.strip()) / 3600
            if age_hours > 25:
                sync_state = 'skipped'
                severity = 'warn'

    status_note = 'No config backup archives found.'
    if running:
        status_note = 'Config backup is currently running.'
        severity = 'warn'
        sync_state = 'running'
    elif artifacts:
        count = len(artifacts)
        size_str = f"~{total_size_gb} GB total" if total_size_gb is not None else "size unknown"
        status_note = f"Detected {count} config archive(s) ({size_str})."

    return {
        **base_info,
        'last_run': last_run,
        'running': running,
        'progress_pct': 50 if running else None,
        'sync_state': sync_state,
        'severity': severity,
        'status_note': status_note,
    }


def _read_backup_overview(automation: dict) -> dict:
    script_entries = {}
    for e in automation.get('cron', []):
        cmd_base = os.path.basename((e.get('command', '').strip().split()[0] if e.get('command') else ''))
        if cmd_base in ('backup-script.sh', 'backup-external.sh', 'proxmox-config-backup.sh'):
            script_entries[cmd_base] = e

    ssh_base, _ = _build_proxmox_ssh_base()
    jobs = []
    for cfg in BACKUP_JOB_DEFS:
        entry = script_entries.get(cfg['script'])
        includes = [f"{cfg['source_root']}/{p} -> {cfg['dest_root']}/{p}" for p in cfg['paths']]
        progress = _running_backup_progress(ssh_base, cfg['script'], cfg['expected_steps'], (entry or {}).get('log_path'))
        sync_state = _backup_sync_state(entry, progress['running'], cfg['expected_steps'], progress['success_count'])

        status_note = (entry or {}).get('status_note') or 'No run status detected yet.'
        if progress['running']:
            status_note = 'Backup is currently running.'

        jobs.append({
            'id': cfg['id'],
            'title': cfg['title'],
            'script': cfg['script'],
            'includes': includes,
            'schedule': (entry or {}).get('schedule') or cfg['schedule_hint'],
            'next_run': (entry or {}).get('next_run'),
            'last_run': (entry or {}).get('last_seen'),
            'running': progress['running'],
            'progress_pct': progress['progress_pct'],
            'sync_state': sync_state,
            'severity': (entry or {}).get('severity', 'warn'),
            'status_note': status_note,
            'log_path': (entry or {}).get('log_path'),
        })

    vm = _read_vm_backup_overview()
    jobs.append(vm)

    config = _read_config_backup_overview(script_entries.get('proxmox-config-backup.sh'))
    jobs.append(config)

    coverage = [
        'Internal: docker-backups, documents, audiobooks, books, games, audiobookshelf, music, other',
        'External: pictures, videos',
        'Proxmox config: /etc/pve, /etc/network, /etc/fstab, /etc/udev, /home/brandon',
        'Proxmox VM archives (vzdump) — managed by Proxmox scheduler (root)',
    ]

    overall = 'ok'
    if any(j.get('severity') == 'crit' for j in jobs):
        overall = 'crit'
    elif any(j.get('severity') == 'warn' for j in jobs):
        overall = 'warn'

    return {
        'severity': overall,
        'jobs': jobs,
        'coverage': coverage,
    }


def _parse_proxmox_cron_line(line: str) -> tuple[str, str] | None:
    s = line.strip()
    if not s or s.startswith('#'):
        return None
    parts = s.split()
    if len(parts) < 6:
        return None
    schedule = ' '.join(parts[:5])
    command = ' '.join(parts[5:])
    return schedule, command


def _read_automation() -> dict:
    cron_entries: list[dict] = []
    timer_entries: list[dict] = []
    container_jobs: list[dict] = []
    user_cron_unavailable = None

    # user crontab
    code, out, err = _run_cmd(['crontab', '-l'], timeout=10)
    if code == 0:
        for ln in out.splitlines():
            parsed = _parse_cron_line(ln)
            if not parsed:
                continue
            schedule, command = parsed
            entry = _normalized_cron_entry('user_crontab', schedule, command)
            if entry:
                cron_entries.append(entry)
    else:
        user_cron_unavailable = {
            'source': 'user_crontab',
            'schedule': None,
            'schedule_human': None,
            'command': f'unavailable: {err or "no crontab"}',
            'description': 'Could not read user crontab from dashboard runtime.',
            'next_run': None,
            'script_exists': None,
            'last_seen': None,
            'last_seen_raw': None,
            'log_path': None,
            'severity': 'warn',
        }

    # host cron files (if mounted)
    spool_candidates = sorted(glob.glob('/host_var_spool_cron/*')) + sorted(glob.glob('/host_var_spool_cron/crontabs/*'))
    for host_file in ['/host_etc/crontab'] + sorted(glob.glob('/host_etc/cron.d/*')) + spool_candidates:
        if not os.path.isfile(host_file):
            continue
        try:
            with open(host_file) as f:
                for ln in f:
                    s = ln.strip()
                    if not s or s.startswith('#'):
                        continue
                    parts = s.split()
                    # /etc/crontab format includes user column
                    if len(parts) >= 7:
                        schedule = ' '.join(parts[:5])
                        command = ' '.join(parts[6:])
                    else:
                        parsed = _parse_cron_line(s)
                        if not parsed:
                            continue
                        schedule, command = parsed
                    entry = _normalized_cron_entry(os.path.basename(host_file), schedule, command)
                    if entry:
                        cron_entries.append(entry)
        except Exception:
            continue

    # Only show the "no user crontab" note if we found no actual cron jobs.
    if not cron_entries and user_cron_unavailable:
        cron_entries.append(user_cron_unavailable)

    # systemd timers (best effort)
    code, out, _ = _run_cmd(['systemctl', 'list-timers', '--all', '--no-pager', '--no-legend'], timeout=15)
    if code == 0:
        for ln in out.splitlines():
            ln = re.sub(r'\s+', ' ', ln.strip())
            if not ln:
                continue
            # NEXT LEFT LAST PASSED UNIT ACTIVATES
            parts = ln.split(' ')
            if len(parts) < 6:
                continue
            unit = parts[-2]
            activates = parts[-1]
            timer_entries.append({
                'unit': unit,
                'activates': activates,
                'raw': ln,
                'severity': 'ok',
            })
    else:
        timer_entries.append({
            'unit': 'systemd-unavailable',
            'activates': 'n/a',
            'raw': 'Systemd timers are not accessible from this container runtime.',
            'severity': 'warn',
        })

    # Optional automation-related container statuses
    for name in AUTOMATION_CONTAINERS:
        code, out, _ = _run_cmd(['docker', 'inspect', '--format', '{{.State.Status}}|{{.State.Health.Status}}', name], timeout=8)
        if code != 0:
            container_jobs.append({'name': name, 'state': 'missing', 'health': None, 'severity': 'warn'})
            continue
        state, health = (out.split('|', 1) + [''])[:2]
        sev = 'ok'
        if state != 'running':
            sev = 'crit'
        elif health and health not in ('healthy', '<no value>'):
            sev = 'warn'
        container_jobs.append({'name': name, 'state': state, 'health': (None if health == '<no value>' else health), 'severity': sev})

    overall = 'ok'
    if any(e.get('severity') == 'crit' for e in cron_entries + timer_entries):
        overall = 'crit'
    elif any(e.get('severity') == 'warn' for e in cron_entries + timer_entries + container_jobs):
        overall = 'warn'

    return {
        'severity': overall,
        'cron': cron_entries,
        'timers': timer_entries,
        'automation_containers': container_jobs,
    }


def _read_mount_inventory() -> dict:
    ignored_fs = {
        'proc', 'sysfs', 'devtmpfs', 'devpts', 'tmpfs', 'overlay', 'squashfs',
        'cgroup', 'cgroup2', 'mqueue', 'pstore', 'debugfs', 'tracefs', 'securityfs'
    }
    mounts: list[dict] = []
    try:
        with open('/proc/mounts') as f:
            for ln in f:
                parts = ln.split()
                if len(parts) < 3:
                    continue
                device, mnt, fs = parts[:3]
                if fs in ignored_fs:
                    continue
                # Hide container runtime internals that overwhelm the UI.
                if '/overlay2/' in mnt or '/containers/' in mnt:
                    continue
                if not (mnt == '/' or mnt.startswith('/mnt/') or mnt.startswith('/home/')):
                    continue
                # Keep mount inventory concise at the top level.
                if mnt.startswith('/mnt/') and mnt.count('/') > 2:
                    continue
                disk = _read_disk(mnt)
                mounts.append({
                    'mountpoint': mnt,
                    'device': device,
                    'fstype': fs,
                    'used_gb': disk['used_gb'],
                    'total_gb': disk['total_gb'],
                    'pct': disk['pct'],
                    'severity': 'crit' if disk['pct'] >= 93 else 'warn' if disk['pct'] >= 85 else 'ok',
                })
    except Exception:
        pass

    # dedupe by mountpoint
    uniq = {}
    for m in mounts:
        uniq[m['mountpoint']] = m
    mounts = sorted(uniq.values(), key=lambda x: x['pct'], reverse=True)

    overall = 'ok'
    if any(m['severity'] == 'crit' for m in mounts):
        overall = 'crit'
    elif any(m['severity'] == 'warn' for m in mounts):
        overall = 'warn'

    return {'severity': overall, 'mounts': mounts}


def _read_network_health() -> dict:
    # default route
    code, route_out, _ = _run_cmd(['ip', 'route', 'show', 'default'], timeout=8)
    default_route = route_out.splitlines()[0] if code == 0 and route_out else None

    # basic connectivity
    ping_ms = None
    internet_up = False
    code, ping_out, _ = _run_cmd(['ping', '-c', '1', '-W', '2', '1.1.1.1'], timeout=5)
    if code == 0:
        internet_up = True
        m = re.search(r'time=([0-9.]+)\s*ms', ping_out)
        if m:
            ping_ms = float(m.group(1))

    # dns test
    dns_ok = False
    code, _, _ = _run_cmd(['getent', 'hosts', 'github.com'], timeout=6)
    if code == 0:
        dns_ok = True

    # tailscale (CLI optional)
    tailscale = {'available': False, 'backend_state': None, 'self_ip': None, 'severity': 'warn'}
    if shutil.which('tailscale'):
        tailscale['available'] = True
        code, out, _ = _run_cmd(['tailscale', 'status', '--json'], timeout=8)
        if code == 0 and out:
            try:
                d = json.loads(out)
                backend = d.get('BackendState')
                tailscale.update({
                    'backend_state': backend,
                    'self_ip': (d.get('Self', {}) or {}).get('TailscaleIPs', [None])[0],
                    'severity': 'ok' if backend == 'Running' else 'warn',
                })
            except Exception:
                tailscale['severity'] = 'warn'
    else:
        # Fall back to interface detection in host net namespace.
        code, out, _ = _run_cmd(['ip', '-o', '-4', 'addr', 'show', 'tailscale0'], timeout=6)
        if code == 0 and out:
            m = re.search(r'inet\s+([0-9.]+/[0-9]+)', out)
            tailscale.update({
                'available': True,
                'backend_state': 'Running (interface detected)',
                'self_ip': m.group(1) if m else None,
                'severity': 'ok',
            })

    # mullvad via container status if present (try exact then fuzzy name match)
    mullvad = {'state': 'unknown', 'health': None, 'severity': 'warn'}
    mullvad_name = 'mullvad-vpn'
    code, out, _ = _run_cmd(['docker', 'inspect', '--format', '{{.State.Status}}|{{.State.Health.Status}}', mullvad_name], timeout=8)
    if code != 0:
        c2, out2, _ = _run_cmd(['sh', '-c', "docker ps -a --format '{{.Names}}' | grep -i mullvad | head -n 1"], timeout=8)
        if c2 == 0 and out2:
            mullvad_name = out2.strip()
            code, out, _ = _run_cmd(['docker', 'inspect', '--format', '{{.State.Status}}|{{.State.Health.Status}}', mullvad_name], timeout=8)
    if code == 0:
        state, health = (out.split('|', 1) + [''])[:2]
        mullvad = {
            'name': mullvad_name,
            'state': state,
            'health': None if health == '<no value>' else health,
            'severity': 'ok' if state == 'running' and health != 'unhealthy' else 'warn',
        }
    else:
        mullvad = {'name': mullvad_name, 'state': 'missing', 'health': None, 'severity': 'warn'}

    # active interfaces
    interfaces: list[dict] = []
    code, out, _ = _run_cmd(['ip', '-o', '-4', 'addr', 'show'], timeout=8)
    if code == 0 and out:
        for ln in out.splitlines():
            m = re.search(r'^\d+:\s+([^\s]+)\s+inet\s+([0-9.]+/[0-9]+)', ln)
            if not m:
                continue
            iface = m.group(1)
            cidr = m.group(2)
            if iface == 'lo':
                continue
            # Filter noisy bridge/docker internals; keep primary + VPN interfaces.
            if iface.startswith('br-') or iface.startswith('docker') or iface.startswith('veth'):
                continue
            interfaces.append({'name': iface, 'addr': cidr})

    # lightweight HTTP probe
    probe = {'ok': False, 'connect_s': None, 'ttfb_s': None, 'download_bytes_per_s': None}
    code, out, _ = _run_cmd([
        'curl', '-sS', '-o', '/dev/null',
        '-w', '%{time_connect}|%{time_starttransfer}|%{speed_download}',
        '--max-time', '8',
        'https://speed.cloudflare.com/__down?bytes=2000000'
    ], timeout=10)
    if code == 0 and out and '|' in out:
        try:
            tc, tt, sp = out.split('|')
            probe = {
                'ok': True,
                'connect_s': float(tc),
                'ttfb_s': float(tt),
                'download_bytes_per_s': float(sp),
            }
        except Exception:
            pass

    # real-time throughput sample over 1 second
    def net_totals() -> tuple[int, int]:
        rx = 0
        tx = 0
        try:
            with open('/proc/net/dev') as f:
                for ln in f.readlines()[2:]:
                    if ':' not in ln:
                        continue
                    iface, vals = ln.split(':', 1)
                    iface = iface.strip()
                    if iface in ('lo',):
                        continue
                    cols = vals.split()
                    if len(cols) >= 10:
                        rx += int(cols[0])
                        tx += int(cols[8])
        except Exception:
            pass
        return rx, tx

    rx1, tx1 = net_totals()
    time.sleep(1)
    rx2, tx2 = net_totals()
    rx_rate = max(rx2 - rx1, 0)
    tx_rate = max(tx2 - tx1, 0)

    overall = 'ok'
    if not internet_up or not dns_ok:
        overall = 'crit'
    elif (tailscale.get('severity') == 'warn') or (mullvad.get('severity') == 'warn'):
        overall = 'warn'

    return {
        'severity': overall,
        'default_route': default_route,
        'internet_up': internet_up,
        'dns_ok': dns_ok,
        'ping_ms': ping_ms,
        'interfaces': interfaces,
        'probe': probe,
        'rx_bytes_per_s': rx_rate,
        'tx_bytes_per_s': tx_rate,
        'tailscale': tailscale,
        'mullvad': mullvad,
    }


def _read_docker_overview() -> dict:
    code, ps_out, _ = _run_cmd(['docker', 'ps', '-a', '--format', '{{.Names}}|{{.Status}}'], timeout=10)
    containers_total = 0
    containers_running = 0
    if code == 0 and ps_out:
        rows = [ln for ln in ps_out.splitlines() if '|' in ln]
        containers_total = len(rows)
        containers_running = sum(1 for ln in rows if ln.split('|', 1)[1].lower().startswith('up'))

    code, img_out, _ = _run_cmd(['sh', '-c', 'docker images -q | wc -l'], timeout=10)
    images_total = int(img_out.strip()) if code == 0 and img_out.strip().isdigit() else 0

    code, dangling_out, _ = _run_cmd(['sh', '-c', 'docker images -f dangling=true -q | wc -l'], timeout=10)
    dangling_images = int(dangling_out.strip()) if code == 0 and dangling_out.strip().isdigit() else 0

    code, vol_out, _ = _run_cmd(['sh', '-c', 'docker volume ls -qf dangling=true | wc -l'], timeout=10)
    dangling_volumes = int(vol_out.strip()) if code == 0 and vol_out.strip().isdigit() else 0

    code, df_out, _ = _run_cmd(['docker', 'system', 'df'], timeout=15)
    reclaimable_summary = None
    if code == 0 and df_out:
        for ln in df_out.splitlines():
            if ln.strip().startswith('Images') or ln.strip().startswith('Containers') or ln.strip().startswith('Local Volumes'):
                continue
            if 'Reclaimable' in ln:
                continue
        m = re.search(r'Total space reclaimable:\s*([^\n]+)', df_out)
        if m:
            reclaimable_summary = m.group(1).strip()

    sev = 'ok'
    if dangling_images > 20 or dangling_volumes > 20:
        sev = 'warn'

    return {
        'severity': sev,
        'containers_total': containers_total,
        'containers_running': containers_running,
        'images_total': images_total,
        'dangling_images': dangling_images,
        'dangling_volumes': dangling_volumes,
        'reclaimable_summary': reclaimable_summary,
    }


def _read_host_config() -> dict:
    fstab_path = '/host_etc/fstab' if os.path.exists('/host_etc/fstab') else '/etc/fstab'
    fstab_entries = 0
    fstab_mounts: list[dict] = []
    if os.path.exists(fstab_path):
        try:
            with open(fstab_path) as f:
                for ln in f:
                    s = ln.strip()
                    if s and not s.startswith('#'):
                        fstab_entries += 1
                        parts = s.split()
                        if len(parts) >= 3:
                            mountpoint = parts[1]
                            fs = parts[2]
                            is_mounted = os.path.ismount(mountpoint)
                            fstab_mounts.append({
                                'mountpoint': mountpoint,
                                'fstype': fs,
                                'mounted': is_mounted,
                                'severity': 'ok' if is_mounted else 'warn',
                            })
        except Exception:
            fstab_entries = 0

    iptables_available = shutil.which('iptables-save') is not None
    iptables_rules = None
    iptables_error = None
    if iptables_available:
        code, out, err = _run_cmd(['iptables-save'], timeout=8)
        if code == 0:
            iptables_rules = len([ln for ln in out.splitlines() if ln.startswith('-A ')])
        else:
            iptables_error = err or 'Permission or runtime access issue'

    return {
        'severity': 'ok' if fstab_entries > 0 else 'warn',
        'fstab_path': fstab_path if os.path.exists(fstab_path) else None,
        'fstab_entries': fstab_entries,
        'fstab_mounts': fstab_mounts,
        'iptables_available': iptables_available,
        'iptables_rules': iptables_rules,
        'iptables_error': iptables_error,
    }


def _read_proxmox_info() -> dict:
    """Best-effort Proxmox backup visibility via optional SSH target env vars."""
    ssh_base, err = _build_proxmox_ssh_base()
    if not ssh_base or err:
        return {
            'severity': 'warn',
            'configured': False,
            'summary': 'Set PROXMOX_SSH_HOST (and key-based SSH) to enable backup visibility',
            'backups': [],
        }

    code, out, err = _run_cmd(ssh_base + ["ls -1t /mnt/backups 2>/dev/null | head -20"], timeout=12)
    if code != 0:
        return {
            'severity': 'warn',
            'configured': True,
            'summary': f'Could not read Proxmox backups: {err or "SSH failed"}',
            'backups': [],
            'mounts': [],
            'cron': [],
        }

    backups = [ln for ln in out.splitlines() if ln.strip()]

    # Proxmox mount inventory
    m_code, m_out, _ = _run_cmd(ssh_base + ["df -h --output=source,size,used,avail,pcent,target /mnt/* 2>/dev/null | tail -n +2"], timeout=12)
    mounts = []
    if m_code == 0 and m_out:
        for ln in m_out.splitlines():
            p = ln.split()
            if len(p) >= 6:
                mounts.append({
                    'source': p[0],
                    'size': p[1],
                    'used': p[2],
                    'avail': p[3],
                    'pcent': p[4],
                    'target': p[5],
                })

    # Proxmox user crontab (defaults to brandon user)
    c_code, c_out, _ = _run_cmd(ssh_base + ["crontab -l 2>/dev/null | sed '/^#/d;/^$/d' | head -50"], timeout=10)
    cron_lines = [ln for ln in c_out.splitlines() if ln.strip()] if c_code == 0 and c_out else []

    backup_logs: dict[str, dict] = {}
    for script_name in ('backup-script.sh', 'backup-external.sh'):
        status = _read_backup_log_status_remote(ssh_base, script_name)
        if status:
            backup_logs[script_name] = status

    sev = 'ok' if backups else 'warn'
    return {
        'severity': sev,
        'configured': True,
        'summary': f'Found {len(backups)} backup item(s) in /mnt/backups',
        'backups': backups,
        'mounts': mounts,
        'cron': cron_lines,
        'backup_logs': backup_logs,
    }


def _collect_extended() -> dict:
    repos = _read_git_repos()
    automation = _read_automation()
    disks = _read_mount_inventory()
    network = _read_network_health()
    docker = _read_docker_overview()
    host_cfg = _read_host_config()
    proxmox = _read_proxmox_info()

    # Merge Proxmox cron jobs into the main automation list for one unified view.
    for ln in proxmox.get('cron', [])[:50]:
        parsed = _parse_proxmox_cron_line(ln)
        if not parsed:
            continue
        schedule, command = parsed
        entry = _normalized_cron_entry('proxmox_root_crontab', schedule, command)
        if entry:
            automation['cron'].append(entry)

    # For backup scripts that now log directly under brandon, prefer remote log status.
    backup_logs = proxmox.get('backup_logs', {}) or {}
    for entry in automation.get('cron', []):
        command = entry.get('command', '')
        cmd_base = os.path.basename((command.strip().split()[0] if command.strip() else ''))
        remote = backup_logs.get(cmd_base)
        if not remote:
            continue
        if remote.get('time'):
            entry['last_seen'] = remote['time']
        if remote.get('log_path'):
            entry['log_path'] = remote['log_path']
        if remote.get('status_note'):
            entry['status_note'] = remote['status_note']
        if remote.get('severity') in ('ok', 'warn', 'crit') and entry.get('severity') != 'crit':
            entry['severity'] = remote['severity']

    backups = _read_backup_overview(automation)

    if any(e.get('severity') == 'crit' for e in automation.get('cron', []) + automation.get('timers', [])):
        automation['severity'] = 'crit'
    elif any(e.get('severity') == 'warn' for e in automation.get('cron', []) + automation.get('timers', []) + automation.get('automation_containers', [])):
        automation['severity'] = 'warn'
    else:
        automation['severity'] = 'ok'

    severities = [repos['severity'], backups['severity'], automation['severity'], disks['severity'], network['severity'], docker['severity'], host_cfg['severity'], proxmox['severity']]
    overall = 'ok'
    if 'crit' in severities:
        overall = 'crit'
    elif 'warn' in severities:
        overall = 'warn'

    return {
        'ts': int(time.time()),
        'overall': overall,
        'repos': repos,
        'backups': backups,
        'automation': automation,
        'disks': disks,
        'network': network,
        'docker': docker,
        'host_config': host_cfg,
        'proxmox': proxmox,
    }


def _overall_from_sections(ext: dict) -> str:
    severities = []
    for key in ('repos', 'backups', 'automation', 'disks', 'network', 'docker', 'host_config', 'proxmox'):
        sev = (ext.get(key) or {}).get('severity') if isinstance(ext.get(key), dict) else None
        if sev:
            severities.append(sev)
    if 'crit' in severities:
        return 'crit'
    if 'warn' in severities:
        return 'warn'
    return 'ok'


def _collect() -> dict:
    cpu        = _read_cpu()
    mem        = _read_mem()
    dsk        = _read_disk('/mnt/docker')
    ssd250     = _read_disk('/mnt/ssd250')
    nas        = _read_disk('/mnt/boston')
    backups    = _read_disk('/mnt/backups')
    external   = _read_disk('/mnt/external')
    ctrs       = _read_containers()
    ctr_stats  = _read_container_stats()   # per-container CPU/RAM for pie charts
    drive_inventory = _read_drive_inventory_remote()

    # Many hosts map Docker data onto /mnt/ssd250; use it when /mnt/docker is unavailable.
    docker_effective = dsk if dsk.get('total_gb', 0) > 0 else ssd250

    # If dashboard is running on a different host namespace, pull selected disk usage from Proxmox.
    remote_disks = _read_proxmox_disks_remote()
    if remote_disks.get('ssd250_disk'):
        ssd250 = remote_disks['ssd250_disk']
    if remote_disks.get('backups_disk'):
        backups = remote_disks['backups_disk']
    if remote_disks.get('external_disk'):
        external = remote_disks['external_disk']

    ram_pct  = int(mem['ram_used_mb']  / mem['ram_total_mb']  * 100) if mem['ram_total_mb']  else 0
    swap_pct = int(mem['swap_used_mb'] / mem['swap_total_mb'] * 100) if mem['swap_total_mb'] else 0

    sevs = [_sev(cpu, 'cpu'), _sev(ram_pct, 'ram'), _sev(swap_pct, 'swap'),
            _sev(docker_effective['pct'], 'docker_disk'), _sev(ssd250['pct'], 'ssd250_disk'),
            _sev(nas['pct'], 'nas_disk'), _sev(backups['pct'], 'backups_disk'),
            _sev(external['pct'], 'external_disk')]
    for d in drive_inventory:
        if d.get('severity') in ('warn', 'crit'):
            sevs.append(d['severity'])
    ctr_problem = any(
        (c['state'] == 'missing' or c['state'] == 'stopped' or c['health'] == 'unhealthy')
        and not (c.get('optional') and c['state'] == 'idle')
        for c in ctrs
    )
    overall = ('crit' if ('crit' in sevs or ctr_problem) else
               'warn' if 'warn' in sevs else 'ok')

    return {
        'ts': int(time.time()),
        'overall': overall,
        'cpu':           {'pct': cpu, 'severity': _sev(cpu, 'cpu')},
        'ram':           {'used_mb': mem['ram_used_mb'], 'total_mb': mem['ram_total_mb'],
                          'pct': ram_pct, 'severity': _sev(ram_pct, 'ram')},
        'swap':          {'used_mb': mem['swap_used_mb'], 'total_mb': mem['swap_total_mb'],
                          'pct': swap_pct, 'severity': _sev(swap_pct, 'swap')},
        'docker_disk':   {**docker_effective, 'severity': _sev(docker_effective['pct'], 'docker_disk')},
        'ssd250_disk':   {**ssd250, 'severity': _sev(ssd250['pct'], 'ssd250_disk')},
        'nas_disk':      {**nas, 'severity': _sev(nas['pct'], 'nas_disk')},
        'backups_disk':  {**backups, 'severity': _sev(backups['pct'], 'backups_disk')},
        'external_disk': {**external, 'severity': _sev(external['pct'], 'external_disk')},
        'drive_inventory': drive_inventory,
        'containers':    ctrs,
        'container_stats': ctr_stats,
        'thresholds':    THRESHOLDS,
    }


def _persist_snap(snap: dict):
    try:
        con = sqlite3.connect(DB_PATH)
        con.execute('INSERT OR REPLACE INTO metrics VALUES (?,?,?,?,?,?,?,?)', (
            snap['ts'],
            snap['cpu']['pct'],
            snap['ram']['used_mb'],  snap['ram']['total_mb'],
            snap['swap']['used_mb'], snap['swap']['total_mb'],
            snap['docker_disk']['pct'], snap['nas_disk']['pct'],
        ))
        con.execute('DELETE FROM metrics WHERE ts < ?', (snap['ts'] - 30 * 86400,))
        con.commit()
        con.close()
    except Exception as ex:
        logger.warning(f'DB write error: {ex}')


def _metrics_loop():
    _init_db()
    loop_count = 0
    while True:
        try:
            snap = _collect()
            _persist_snap(snap)
            with _status_lock:
                _latest_status.clear()
                _latest_status.update(snap)

            # Extended checks are heavier; refresh every 5 minutes.
            if loop_count % 5 == 0:
                ext = _collect_extended()
                with _extended_lock:
                    _latest_extended.clear()
                    _latest_extended.update(ext)
        except Exception as ex:
            logger.warning(f'Metrics collection error: {ex}')
        loop_count += 1
        time.sleep(60)


# Kick off background collector immediately on startup
threading.Thread(target=_metrics_loop, daemon=True, name='metrics-collector').start()


@app.route('/api/restart/<service_id>', methods=['POST'])
def restart_container(service_id):
    """Restart a Docker container."""
    if service_id not in CONTAINERS:
        return jsonify({'error': 'Unknown service'}), 404

    container_name = CONTAINERS[service_id]['name']

    try:
        logger.info(f"Restarting container: {container_name}")
        result = subprocess.run(
            ['docker', 'restart', container_name],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            logger.info(f"Successfully restarted {container_name}")
            return jsonify({'success': True, 'message': f'Restarted {container_name}'})
        else:
            logger.error(f"Failed to restart {container_name}: {result.stderr}")
            return jsonify({'error': result.stderr}), 500

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Restart timed out'}), 500
    except Exception as e:
        logger.error(f"Error restarting {container_name}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/recreate/<service_id>', methods=['POST'])
def recreate_container(service_id):
    """Recreate a Docker container using docker compose."""
    if service_id not in CONTAINERS:
        return jsonify({'error': 'Unknown service'}), 404

    compose_dir = CONTAINERS[service_id]['compose_dir']
    container_name = CONTAINERS[service_id]['name']
    service_name = CONTAINERS[service_id]['service']

    try:
        logger.info(f"Recreating container: {container_name} (service: {service_name}) in {compose_dir}")
        result = subprocess.run(
            ['docker', 'compose', 'up', '-d', '--force-recreate', service_name],
            cwd=compose_dir if compose_dir.startswith('/') else f'/home/brandon/projects/docker/{compose_dir}',
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            logger.info(f"Successfully recreated {container_name}")
            return jsonify({'success': True, 'message': f'Recreated {container_name}'})
        else:
            logger.error(f"Failed to recreate {container_name}: {result.stderr}")
            return jsonify({'error': result.stderr}), 500

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Recreate timed out'}), 500
    except Exception as e:
        logger.error(f"Error recreating {container_name}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/scan/jellyfin', methods=['POST'])
def scan_jellyfin():
    """Trigger a library scan on Jellyfin."""
    try:
        # Jellyfin API endpoint for library refresh
        # Note: This requires an API key to be configured in Jellyfin
        # Users should set the JELLYFIN_API_KEY environment variable
        api_key = os.environ.get('JELLYFIN_API_KEY', '')

        if not api_key:
            return jsonify({'error': 'JELLYFIN_API_KEY environment variable not set'}), 500

        jellyfin_url = 'http://100.123.154.40:8096'
        url = f'{jellyfin_url}/Library/Refresh?api_key={api_key}'

        logger.info(f"Triggering Jellyfin library scan")
        response = requests.post(url, timeout=10)

        if response.status_code == 204 or response.status_code == 200:
            logger.info("Successfully triggered Jellyfin library scan")
            return jsonify({'success': True, 'message': 'Jellyfin library scan started'})
        else:
            logger.error(f"Failed to trigger Jellyfin scan: {response.status_code}")
            return jsonify({'error': f'Jellyfin API returned status {response.status_code}'}), 500

    except requests.exceptions.Timeout:
        return jsonify({'error': 'Request to Jellyfin timed out'}), 500
    except Exception as e:
        logger.error(f"Error triggering Jellyfin scan: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/scan/audiobookshelf', methods=['POST'])
def scan_audiobookshelf():
    """Trigger a library scan on Audiobookshelf."""
    try:
        # Audiobookshelf API endpoint for library scan
        # Note: This requires an API token to be configured
        # Users should set the AUDIOBOOKSHELF_API_TOKEN environment variable
        api_token = os.environ.get('AUDIOBOOKSHELF_API_TOKEN', '')

        if not api_token:
            return jsonify({'error': 'AUDIOBOOKSHELF_API_TOKEN environment variable not set'}), 500

        audiobookshelf_url = 'http://100.123.154.40:13378'

        # First, get the library ID (assuming first library, or we could make this configurable)
        headers = {'Authorization': f'Bearer {api_token}'}
        libraries_url = f'{audiobookshelf_url}/api/libraries'

        logger.info(f"Getting Audiobookshelf libraries")
        libraries_response = requests.get(libraries_url, headers=headers, timeout=10)

        if libraries_response.status_code != 200:
            logger.error(f"Failed to get Audiobookshelf libraries: {libraries_response.status_code}")
            return jsonify({'error': f'Failed to get libraries: {libraries_response.status_code}'}), 500

        libraries = libraries_response.json().get('libraries', [])
        if not libraries:
            return jsonify({'error': 'No libraries found in Audiobookshelf'}), 404

        # Scan all libraries
        scan_results = []
        for library in libraries:
            library_id = library.get('id')
            scan_url = f'{audiobookshelf_url}/api/libraries/{library_id}/scan'

            logger.info(f"Triggering Audiobookshelf library scan for library {library_id}")
            scan_response = requests.post(scan_url, headers=headers, timeout=10)

            if scan_response.status_code == 200:
                scan_results.append(f"Library {library.get('name', library_id)} scan started")
            else:
                scan_results.append(f"Library {library.get('name', library_id)} scan failed")

        logger.info("Successfully triggered Audiobookshelf library scans")
        return jsonify({'success': True, 'message': ', '.join(scan_results)})

    except requests.exceptions.Timeout:
        return jsonify({'error': 'Request to Audiobookshelf timed out'}), 500
    except Exception as e:
        logger.error(f"Error triggering Audiobookshelf scan: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tag/stash', methods=['POST'])
def tag_stash():
    """Trigger auto-tagging on Stash via its GraphQL API."""
    try:
        api_key = os.environ.get('STASH_API_KEY', '')

        if not api_key:
            return jsonify({'error': 'STASH_API_KEY environment variable not set'}), 500

        stash_url = 'http://100.123.154.40:9999'
        graphql_url = f'{stash_url}/graphql'

        headers = {
            'Content-Type': 'application/json',
            'ApiKey': api_key,
        }

        # Auto-tag all scenes against all performers, studios, and tags
        # Using ["*"] signals Stash to match everything
        query = """
        mutation MetadataAutoTag {
            metadataAutoTag(input: {performers: ["*"], studios: ["*"], tags: ["*"]})
        }
        """

        logger.info("Triggering Stash auto-tagging")
        response = requests.post(
            graphql_url,
            json={'query': query},
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            if 'errors' in data:
                logger.error(f"Stash GraphQL errors: {data['errors']}")
                return jsonify({'error': str(data['errors'])}), 500
            logger.info("Successfully triggered Stash auto-tagging")
            return jsonify({'success': True, 'message': 'Stash auto-tagging started'})
        elif response.status_code == 401:
            return jsonify({'error': 'Authentication failed. Check STASH_API_KEY.'}), 500
        else:
            logger.error(f"Failed to trigger Stash auto-tagging: {response.status_code}")
            return jsonify({'error': f'Stash API returned status {response.status_code}'}), 500

    except requests.exceptions.Timeout:
        return jsonify({'error': 'Request to Stash timed out'}), 500
    except Exception as e:
        logger.error(f"Error triggering Stash auto-tagging: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/youtube', methods=['POST'])
def download_youtube():
    """Download YouTube video as MP3 audio or full video using yt-dlp."""
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({'error': 'YouTube URL is required'}), 400

        youtube_url = data['url'].strip()
        if not youtube_url:
            return jsonify({'error': 'YouTube URL cannot be empty'}), 400

        # Basic URL validation
        if not ('youtube.com' in youtube_url or 'youtu.be' in youtube_url):
            return jsonify({'error': 'Invalid YouTube URL'}), 400

        # Get download type (default to mp3 for backward compatibility)
        download_type = data.get('type', 'mp3').lower()

        logger.info(f"Starting YouTube download ({download_type}) for URL: {youtube_url}")

        # Build yt-dlp command based on download type
        if download_type == 'video':
            # Download full video in best quality with robust retry options
            cmd = [
                'docker', 'exec', 'yt-dlp-web', 'yt-dlp',
                '--format', 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio/best[ext=mp4]/best',
                '--merge-output-format', 'mp4',
                '--add-metadata',
                '--no-part',
                '--retries', '10',
                '--fragment-retries', '10',
                '--file-access-retries', '10',
                '--output', '/downloads/video/%(title)s.%(ext)s',
                youtube_url
            ]
            success_msg = 'Video download completed! File saved to /mnt/boston/media/downloads/youtube/video/'
        else:
            # Download audio as MP3 (default)
            cmd = [
                'docker', 'exec', 'yt-dlp-web', 'yt-dlp',
                '--extract-audio',
                '--audio-format', 'mp3',
                '--audio-quality', '0',
                '--embed-thumbnail',
                '--add-metadata',
                '--parse-metadata', '%(title)s:%(meta_title)s',
                '--parse-metadata', '%(uploader)s:%(meta_artist)s',
                '--output', '/downloads/music/%(title)s.%(ext)s',
                youtube_url
            ]
            success_msg = 'MP3 download completed! File saved to /mnt/boston/media/downloads/youtube/music/'

        # Run yt-dlp inside the yt-dlp-web container
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout for download
        )

        if result.returncode == 0:
            logger.info(f"Successfully downloaded YouTube {download_type}: {youtube_url}")
            return jsonify({
                'success': True,
                'message': success_msg
            })
        else:
            logger.error(f"Failed to download YouTube {download_type}: {result.stderr}")
            return jsonify({'error': f'Download failed: {result.stderr}'}), 500

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Download timed out (max 5 minutes)'}), 500
    except Exception as e:
        logger.error(f"Error downloading YouTube video: {str(e)}")
        return jsonify({'error': str(e)}), 500

def _delayed_self_command(cmd, delay=1.0):
    """Run a command after a delay in a background thread (fire-and-forget)."""
    def run():
        import time
        time.sleep(delay)
        logger.info(f"Executing delayed self-command: {' '.join(cmd)}")
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t = threading.Thread(target=run, daemon=True)
    t.start()

@app.route('/api/self/restart', methods=['POST'])
def self_restart():
    """Restart the dashboard container itself. Returns immediately, then restarts."""
    logger.info("Self-restart requested")
    _delayed_self_command(['docker', 'restart', 'dashboard'], delay=0.5)
    return jsonify({'success': True, 'message': 'Dashboard is restarting...'})

@app.route('/api/self/recreate', methods=['POST'])
def self_recreate():
    """Recreate the dashboard container itself via a sibling container.

    We can't run 'docker compose up --force-recreate' from inside the container
    being recreated — Docker kills us before starting the replacement. Instead,
    spin up a short-lived sibling container that performs the recreate for us.
    """
    logger.info("Self-recreate requested — spawning sibling recreator container")

    def run():
        import time
        time.sleep(0.5)
        # Clean up any leftover recreator
        subprocess.run(['docker', 'rm', '-f', 'dashboard-recreator'],
                       capture_output=True, timeout=5)
        # Spawn a detached sibling container that does the actual recreate.
        # It shares the docker socket and has the dashboard source mounted.
        subprocess.Popen([
            'docker', 'run', '--rm', '-d',
            '--name', 'dashboard-recreator',
            '-v', '/var/run/docker.sock:/var/run/docker.sock',
            '-v', '/home/brandon/projects/Dashboard:/workspace',
            '-w', '/workspace',
            'dashboard-dashboard',
            'sh', '-c', 'sleep 1 && docker compose up -d --force-recreate --build dashboard'
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return jsonify({'success': True, 'message': 'Dashboard is recreating...'})

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok'})

# --- Bookmarks Feature ---
BOOKMARKS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'bookmarks.json')

def _ensure_bookmarks_dir():
    os.makedirs(os.path.dirname(BOOKMARKS_FILE), exist_ok=True)

def _load_bookmarks():
    _ensure_bookmarks_dir()
    if not os.path.exists(BOOKMARKS_FILE):
        return []
    with open(BOOKMARKS_FILE, 'r') as f:
        return json.load(f)

def _save_bookmarks(bookmarks):
    _ensure_bookmarks_dir()
    with open(BOOKMARKS_FILE, 'w') as f:
        json.dump(bookmarks, f, indent=2)

@app.route('/api/bookmarks', methods=['GET'])
def get_bookmarks():
    """Get all bookmarks."""
    return jsonify(_load_bookmarks())

@app.route('/api/bookmarks', methods=['POST'])
def add_bookmark():
    """Add a new bookmark or folder."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    bookmark = {
        'id': str(uuid.uuid4()),
        'name': data.get('name', 'Untitled'),
        'url': data.get('url', ''),
        'type': data.get('type', 'bookmark'),  # 'bookmark' or 'folder'
        'parent_id': data.get('parent_id', None),
        'created': datetime.now().isoformat(),
    }

    bookmarks = _load_bookmarks()
    bookmarks.append(bookmark)
    _save_bookmarks(bookmarks)
    return jsonify(bookmark), 201

@app.route('/api/bookmarks/<bookmark_id>', methods=['PUT'])
def update_bookmark(bookmark_id):
    """Update a bookmark."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    bookmarks = _load_bookmarks()
    for bm in bookmarks:
        if bm['id'] == bookmark_id:
            bm['name'] = data.get('name', bm['name'])
            bm['url'] = data.get('url', bm['url'])
            bm['parent_id'] = data.get('parent_id', bm.get('parent_id'))
            _save_bookmarks(bookmarks)
            return jsonify(bm)
    return jsonify({'error': 'Bookmark not found'}), 404

@app.route('/api/bookmarks/<bookmark_id>', methods=['DELETE'])
def delete_bookmark(bookmark_id):
    """Delete a bookmark and any children (if folder)."""
    bookmarks = _load_bookmarks()

    # Collect IDs to delete (the target + all descendants)
    def collect_ids(parent_id):
        ids = {parent_id}
        for bm in bookmarks:
            if bm.get('parent_id') == parent_id:
                ids |= collect_ids(bm['id'])
        return ids

    ids_to_delete = collect_ids(bookmark_id)
    new_bookmarks = [bm for bm in bookmarks if bm['id'] not in ids_to_delete]

    if len(new_bookmarks) == len(bookmarks):
        return jsonify({'error': 'Bookmark not found'}), 404

    _save_bookmarks(new_bookmarks)
    return jsonify({'success': True, 'deleted': len(bookmarks) - len(new_bookmarks)})

@app.route('/')
def index():
    """Serve the main dashboard page."""
    return send_from_directory('static', 'index.html')

@app.route('/bookmarks')
def bookmarks_page():
    """Serve the bookmarks page."""
    return send_from_directory('static', 'bookmarks.html')

@app.route('/server-health')
def server_health_page():
    """Serve the Server Health page."""
    return send_from_directory('static', 'infra.html')

@app.route('/api/infra/status')
def infra_status():
    """Return the latest cached infrastructure snapshot."""
    with _status_lock:
        snap = dict(_latest_status)
    if not snap:
        return jsonify({'error': 'collecting', 'overall': 'unknown'}), 202
    return jsonify(snap)


@app.route('/api/infra/extended')
def infra_extended():
    """Return heavier infrastructure checks (git, automation, disks, network, docker, host config)."""
    with _extended_lock:
        snap = dict(_latest_extended)
    if not snap:
        # Fall back to on-demand collection if startup race occurs.
        try:
            snap = _collect_extended()
        except Exception as ex:
            return jsonify({'error': str(ex), 'overall': 'unknown'}), 500

    # Always refresh git repo status live so UI reflects commits/changes quickly.
    try:
        snap['repos'] = _read_git_repos()
        snap['ts'] = int(time.time())
        snap['overall'] = _overall_from_sections(snap)
    except Exception as ex:
        logger.warning(f'Live repo refresh failed: {ex}')
    return jsonify(snap)

@app.route('/api/infra/history')
def infra_history():
    """Return time-series metrics from SQLite for chart rendering."""
    hours = int(request.args.get('hours', 24))
    since = int(time.time()) - hours * 3600
    try:
        con = sqlite3.connect(DB_PATH)
        rows = con.execute(
            'SELECT ts, cpu_pct, ram_used_mb, ram_total_mb, '
            '       swap_used_mb, swap_total_mb, docker_disk_pct, nas_disk_pct '
            'FROM metrics WHERE ts >= ? ORDER BY ts',
            (since,)
        ).fetchall()
        con.close()
    except Exception as ex:
        return jsonify({'error': str(ex)}), 500
    return jsonify([{
        'ts':             r[0],
        'cpu_pct':        r[1],
        'ram_pct':        int(r[2] / r[3] * 100) if r[3] else 0,
        'swap_pct':       int(r[4] / r[5] * 100) if r[5] else 0,
        'docker_disk_pct': r[6],
        'nas_disk_pct':   r[7],
    } for r in rows])

# ── Fileshare ─────────────────────────────────────────────────────────────────
FILESHARE_NET = 'fileshare-net'
CF_TUNNEL_TOKEN = os.environ.get('CF_TUNNEL_TOKEN', '').strip()
CF_TUNNEL_HOSTNAME = os.environ.get('CF_TUNNEL_HOSTNAME', '').strip()


def _get_tunnel_url():
    """Return the tunnel URL — stable hostname if using a named tunnel, else scrape logs."""
    if CF_TUNNEL_HOSTNAME:
        return f'http://{CF_TUNNEL_HOSTNAME}'
    try:
        logs = subprocess.run(
            ['docker', 'logs', 'fileshare-cloudflared'],
            capture_output=True, text=True, timeout=5
        )
        match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', logs.stdout + logs.stderr)
        return match.group(0) if match else None
    except Exception:
        return None


def _stop_fileshare():
    """Remove fileshare containers and network (best-effort)."""
    subprocess.run(['docker', 'rm', '-f', 'fileshare-miniserve', 'fileshare-cloudflared'],
                   capture_output=True, timeout=15)
    subprocess.run(['docker', 'network', 'rm', FILESHARE_NET], capture_output=True, timeout=10)


@app.route('/api/browse')
def browse():
    """List directory entries for the file browser."""
    path = request.args.get('path', '/').rstrip('/') or '/'
    try:
        entries = []
        with os.scandir(path) as it:
            for e in sorted(it, key=lambda x: (not x.is_dir(follow_symlinks=False), x.name.lower())):
                try:
                    size = e.stat().st_size if e.is_file(follow_symlinks=False) else None
                except OSError:
                    size = None
                entries.append({
                    'name':   e.name,
                    'path':   os.path.join(path, e.name),
                    'is_dir': e.is_dir(follow_symlinks=False),
                    'size':   size,
                })
        parent = os.path.dirname(path) if path != '/' else None
        return jsonify({'path': path, 'parent': parent, 'entries': entries})
    except PermissionError:
        return jsonify({'error': 'Permission denied'}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/share/start', methods=['POST'])
def share_start():
    """Start a Quick Tunnel fileshare for one or more paths."""
    data = request.get_json() or {}
    paths = data.get('paths') or ([data['path']] if data.get('path') else [])
    paths = [p.strip() for p in paths if p.strip()]
    title = (data.get('title') or 'Quick Share').strip()

    if not paths:
        return jsonify({'error': 'No paths provided'}), 400
    for p in paths:
        if not os.path.exists(p):
            return jsonify({'error': f'Path not found: {p}'}), 400

    try:
        _stop_fileshare()

        subprocess.run(
            ['docker', 'network', 'create', '--driver', 'bridge', FILESHARE_NET],
            capture_output=True, timeout=10
        )

        cmd = ['docker', 'run', '-d', '--name', 'fileshare-miniserve', '--network', FILESHARE_NET]
        for p in paths:
            name = os.path.basename(p.rstrip('/'))
            cmd += ['-v', f'{p}:/share/{name}:ro']
        cmd += ['svenstaro/miniserve:latest', '--interfaces', '0.0.0.0', '--port', '8080',
                '--title', title, '/share']
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            logger.error(f'Fileshare miniserve start failed: {r.stderr}')
            return jsonify({'error': r.stderr}), 500

        cf_cmd = ['docker', 'run', '-d', '--name', 'fileshare-cloudflared', '--network', FILESHARE_NET,
                  'cloudflare/cloudflared:latest', 'tunnel', '--no-autoupdate']
        if CF_TUNNEL_TOKEN:
            cf_cmd += ['run', '--token', CF_TUNNEL_TOKEN]
        else:
            cf_cmd += ['--url', 'http://fileshare-miniserve:8080']
        r = subprocess.run(cf_cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            logger.error(f'Fileshare cloudflared start failed: {r.stderr}')
            return jsonify({'error': r.stderr}), 500

        # Named tunnel URL is known immediately; Quick Tunnel needs log polling
        if CF_TUNNEL_HOSTNAME:
            url = f'http://{CF_TUNNEL_HOSTNAME}'
            # Brief wait for tunnel to come up before returning
            time.sleep(3)
        else:
            url = None
            for _ in range(20):
                time.sleep(1)
                url = _get_tunnel_url()
                if url:
                    break

        logger.info(f'Fileshare started: paths={paths} url={url}')
        return jsonify({'success': True, 'url': url, 'paths': paths})

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Timed out starting fileshare'}), 500
    except Exception as e:
        logger.error(f'Fileshare start error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/share/stop', methods=['POST'])
def share_stop():
    """Stop and remove fileshare containers."""
    try:
        _stop_fileshare()
        logger.info('Fileshare stopped')
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f'Fileshare stop error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/share/status', methods=['GET'])
def share_status():
    """Return current fileshare state: running, URL, and paths being shared."""
    try:
        inspect = subprocess.run(
            ['docker', 'inspect', '--format', '{{.State.Running}}', 'fileshare-cloudflared'],
            capture_output=True, text=True, timeout=5
        )
        running = inspect.stdout.strip() == 'true'
        url = _get_tunnel_url() if running else None

        paths = []
        if running:
            mounts = subprocess.run(
                ['docker', 'inspect', '--format',
                 '{{range .Mounts}}{{.Source}}|{{.Destination}}\n{{end}}',
                 'fileshare-miniserve'],
                capture_output=True, text=True, timeout=5
            )
            for line in mounts.stdout.strip().splitlines():
                if '|' in line:
                    src, dst = line.split('|', 1)
                    if dst.strip().startswith('/share/'):
                        paths.append(src.strip())

        return jsonify({'running': running, 'url': url, 'paths': paths})
    except Exception as e:
        return jsonify({'running': False, 'url': None, 'paths': [], 'error': str(e)})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8001, debug=False)

