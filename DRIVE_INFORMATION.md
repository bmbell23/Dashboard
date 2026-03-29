# Drive Information

Last updated: 2026-03-29

## Changes Made

| Item                                   | Details                                                                 |
|----------------------------------------|-------------------------------------------------------------------------|
| boston backups -> boston_backups       | Renamed in storage config to backup job, no data moved.                |
| Allston moved to isos role             | Allston is now used for ISOs/images, not VM disk storage.              |
| SSD upgraded from previous Allston disk| Prior 128GB drive replaced with 224GB SSD (`ssd250`).                  |
| boston backups typo cleanup            | Naming standardized to reduce typo-prone references.                   |

## Drive Inventory (7 Tracked)

### Internal

| Name      | Device    | Size      | Type      | Interface | Mount             | Status    | Purpose                           |
|-----------|-----------|-----------|-----------|-----------|-------------------|-----------|-----------------------------------|
| nvme      | nvme0n1   | 233 GB    | NVMe SSD  | NVMe      | `/` (LVM)         | Mounted   | Proxmox OS, VM disks, swap        |
| boston    | sda       | 7.3 TB    | HDD       | SATA      | `/mnt/boston`     | Mounted   | VM backups and bulk storage       |
| ssd250    | sdb       | 224 GB    | SSD       | SATA      | `/mnt/ssd250`     | Mounted   | Extra VM storage (VM 100 disks)   |
| backups   | sdc       | 932 GB    | SSD       | SATA      | `/mnt/backups`    | Mounted   | Local file backups (`CLEAN_E`)    |

### External

| Name        | Device    | Size      | Type      | Interface | Mount           | Status      | Purpose                                  |
|-------------|-----------|-----------|-----------|-----------|-----------------|-------------|------------------------------------------|
| allston     | sdd       | 1.8 TB    | HDD       | USB       | `/mnt/allston`  | Mounted     | Proxmox ISO/image storage                |
| external    | sdf       | 1.8 TB    | HDD       | USB       | `/mnt/external` | Mounted     | Personal files, docs, media              |
| flash drive | sde       | 14 GB     | Flash     | USB       | (none)          | Unknown*    | Temporary portable storage (`ESD-USB`)   |

## Proxmox Storage Mapping

| Storage Name      | Path                          | Stores                      | Backing Drive                      |
|-------------------|-------------------------------|-----------------------------|------------------------------------|
| local             | `/var/lib/vz`                 | ISOs, templates, backups    | NVMe (`pve-root`)                  |
| local-lvm         | LVM thin pool                 | VM disks and containers     | NVMe                               |
| isos              | `/mnt/allston/isos`           | ISOs and images             | Allston                            |
| boston_backups    | `/mnt/boston/proxmox-backups` | VM backups                  | Boston                             |
| ssd250            | `/mnt/ssd250`                 | VM images/templates         | ssd250                             |

## Proxmox Backup Job: boston_backups

Location:

`/mnt/boston/proxmox-backups`

| Field          | Value                                                            |
|----------------|------------------------------------------------------------------|
| Schedule       | Every Sunday at 03:00                                            |
| Scope          | All VMs: 101 DockerHost, 100 Windows, 102 Windows, 103 macOS     |
| Format         | `vzdump` (compressed VMA archive)                                |
| Retention      | Last 3 weeks (`keep-weekly=3`)                                   |
| Latest Found   | Latest archive found in `/mnt/boston/proxmox-backups/dump`       |
| Total Size     | ~519 GB currently on disk (`du -sh /mnt/boston/proxmox-backups`) |

Note:

VM 102 (Windows) currently backs up EFI/TPM only (no main disk), which is expected and produces a small archive.

## ISO Storage Data

ISO library path:

`/mnt/allston/isos`

| Path/Folder                    | Status   | Notes                          |
|--------------------------------|----------|--------------------------------|
| `/mnt/allston/isos/template`   | Present  | ISO templates folder exists    |
| `/mnt/allston/isos/images`     | Present  | VM image folder exists         |
| `/mnt/allston/isos/dump`       | Present  | Dump folder exists             |

Note:

ISOs are typically mounted only when creating or modifying VMs.

## External Drive Status (USB)

| Device / Mount             | Status      | Notes                                                      |
|----------------------------|-------------|------------------------------------------------------------|
| Allston at boot            | Inconsistent| May require manual mount depending on attach timing        |
| Allston after boot         | Yes         | Manual mount works; currently mounted on `/mnt/allston`    |
| Allston NTFS               | Yes         | Proxmox access working                                     |
| Flash drive (`sde1`)       | Unknown*    | Detected by `lsblk`, currently no mountpoint shown         |
| Other occasional USB media | Intermittent| Appears when connected                                     |

## VM Placement Snapshot

| VM             | State     | Main Storage            | Notes                      |
|----------------|-----------|-------------------------|----------------------------|
| 101 DockerHost | Running   | local-lvm (NVMe)        | Primary active workload    |
| 100 Windows    | Stopped   | ssd250                  | Main disk on internal SSD  |
| 102 Windows    | Stopped   | local-lvm (EFI/TPM only)| No main OS disk            |
| 103 macOS      | Stopped   | N/A                     | No disks assigned yet      |

## In-Progress Changes

- Confirming whether flash drive should be auto-mounted and where.
- Tightening backup dashboard labels for boston_backups naming.
- Collecting additional USB metadata for dashboard/UI cleanup.

*Unknown = device is detected, but no active mountpoint is currently shown by host `lsblk`/`mount` output.
