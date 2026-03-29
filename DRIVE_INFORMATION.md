# Drive Information

Last updated: 2026-03-29

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
| allston     | sdd       | 1.8 TB    | HDD       | USB       | `/mnt/allston`  | Not mounted | Planned Proxmox ISO storage              |
| external    | sdf       | 1.8 TB    | HDD       | USB       | `/mnt/external` | Mounted     | Personal files, docs, media              |
| flash drive | sde       | 14 GB     | Flash     | USB       | (none)          | Not mounted | Temporary portable storage (`ESD-USB`)   |

## Proxmox Storage Mapping

| Storage Name      | Path                          | Stores                      | Backing Drive                      |
|-------------------|-------------------------------|-----------------------------|------------------------------------|
| local             | `/var/lib/vz`                 | ISOs, templates, backups    | NVMe (`pve-root`)                  |
| local-lvm         | LVM thin pool                 | VM disks and containers     | NVMe                               |
| isos              | `/mnt/allston/isos`           | ISOs and images             | Allston (currently not mounted)    |
| boston backups    | `/mnt/boston/proxmox-backups` | VM backups                  | Boston                             |
| ssd250            | `/mnt/ssd250`                 | VM images/templates         | ssd250                             |

## VM Placement Snapshot

| VM             | State     | Main Storage            | Notes                      |
|----------------|-----------|-------------------------|----------------------------|
| 101 DockerHost | Running   | local-lvm (NVMe)        | Primary active workload    |
| 100 Windows    | Stopped   | ssd250                  | Main disk on internal SSD  |
| 102 Windows    | Stopped   | local-lvm (EFI/TPM only)| No main OS disk            |
| 103 macOS      | Stopped   | N/A                     | No disks assigned yet      |

## In-Progress Changes

- Mounting `allston`.
- Renaming `boston backups` storage entry.
- Collecting additional drive metadata for dashboard/UI cleanup.
