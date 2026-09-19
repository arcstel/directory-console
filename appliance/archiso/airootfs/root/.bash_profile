#
# ~/.bash_profile
#

[[ -f ~/.bashrc ]] && . ~/.bashrc

if grep -q 'janus.installer' /proc/cmdline 2>/dev/null && [ ! -e /run/janus-gui-launched ]; then
  touch /run/janus-gui-launched
  exec /usr/local/bin/janus-gui-install
fi

/usr/local/bin/janus-banner
