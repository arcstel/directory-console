#!/usr/bin/env bash
# shellcheck disable=SC2034

iso_name="janusos"
iso_label="JANUS_$(date +%Y%m)"
iso_publisher="JanusOS"
iso_application="JanusOS Identity Appliance"
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
  ["/etc/janus/janus.env"]="0:0:600"
  ["/opt/janusos"]="0:0:755"
  ["/usr/local/bin/janus-provision"]="0:0:755"
  ["/usr/local/bin/janus-seed"]="0:0:755"
  ["/usr/local/bin/janus-banner"]="0:0:755"
  ["/usr/local/bin/janus-install"]="0:0:755"
  ["/usr/local/bin/janus-gui-install"]="0:0:755"
  ["/root/customize_airootfs.sh"]="0:0:755"
)
