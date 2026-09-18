#!/usr/bin/env bash
# shellcheck disable=SC2034

iso_name="dcc-appliance"
iso_label="DCC_$(date +%Y%m)"
iso_publisher="Directory Control Center"
iso_application="Directory Control Center Appliance"
iso_version="$(date +%Y.%m.%d)"
install_dir="arch"
buildmodes=('iso')
bootmodes=('bios.syslinux' 'uefi.systemd-boot')
arch="x86_64"
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'xz' '-Xbcj' 'x86' '-b' '1M' '-noappend')
bootstrap_tarball_compression=('zstd' '-c' '-T0' '--auto-threads=logical' '-19')

file_permissions=(
  ["/etc/dcc/dcc.env"]="0:0:600"
  ["/opt/directory-console"]="0:0:755"
  ["/usr/local/bin/dcc-provision"]="0:0:755"
  ["/usr/local/bin/dcc-seed"]="0:0:755"
  ["/usr/local/bin/dcc-banner"]="0:0:755"
  ["/root/customize_airootfs.sh"]="0:0:755"
)
