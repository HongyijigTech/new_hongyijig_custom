#!/usr/bin/env bash
set -euo pipefail

ssh -tt hongyi-jig-erp@10.10.71.37 '
set -eu
umask 077
mkdir -p "$HOME/.ssh"
touch "$HOME/.ssh/authorized_keys"
public_key="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILgwb1ZHI9y70nb3NWiEpRJO8VurVy4op+1D/EYpXcBP codex-sseries-staging-autopilot"
grep -qxF "$public_key" "$HOME/.ssh/authorized_keys" || printf "%s\n" "$public_key" >> "$HOME/.ssh/authorized_keys"
chmod 700 "$HOME/.ssh"
chmod 600 "$HOME/.ssh/authorized_keys"

sudo -k
sudoers_rule="hongyi-jig-erp ALL=(root) NOPASSWD: /usr/bin/systemctl start odoo.service, /usr/bin/systemctl stop odoo.service, /usr/bin/systemctl restart odoo.service, /usr/bin/systemctl is-active odoo.service, /usr/bin/systemctl status odoo.service"
printf "%s\n" "$sudoers_rule" | sudo /usr/bin/tee /etc/sudoers.d/hjig-sseries-staging >/dev/null
sudo /bin/chmod 0440 /etc/sudoers.d/hjig-sseries-staging
sudo /usr/sbin/visudo -cf /etc/sudoers.d/hjig-sseries-staging
printf "\nHJIG_AUTOPILOT_ACCESS_READY\n"
'
