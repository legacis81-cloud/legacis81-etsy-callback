#!/bin/bash
# LEGACIS81 - installation de la surveillance sur Oracle A1 (lancé par cs_setup.sh)
# Les codes sont tapés par Loïc ; ils ne sont jamais affichés ni envoyés ailleurs.
set -u
cd "$(dirname "$0")"
ok(){ echo -e "\e[32m✔ $*\e[0m"; }
ko(){ echo -e "\e[31m✘ $*\e[0m"; }
say(){ echo -e "\n\e[33m➜ $*\e[0m"; }

say "1/6 Vérification du serveur"
python3 -c 'import sys; assert sys.version_info>=(3,8)' && ok "Python $(python3 -V 2>&1)" || { ko "Python 3.8+ absent"; exit 1; }
if curl -s -m 10 -o /dev/null https://api.telegram.org; then ok "Accès Internet (Telegram)"; else ko "Le serveur n'a pas accès à Internet (Telegram). Stop : envoie une capture au RCO."; exit 2; fi
if python3 -c 'import socket; socket.create_connection(("imap.gmail.com",993),10)'; then ok "Accès Gmail (IMAP)"; else ko "Gmail injoignable. Stop : capture au RCO."; exit 2; fi

say "2/6 Tes deux codes (rien ne s'affiche quand tu colles, c'est normal)"
read -rsp "Colle la clé du bot Telegram puis Entrée : " TGT; echo
read -rsp "Colle le code Gmail de 16 lettres puis Entrée : " GPW; echo
GPW=$(echo "$GPW" | tr -d ' ')
[ ${#GPW} -eq 16 ] || { ko "Le code Gmail doit faire 16 lettres (reçu ${#GPW}). Relance le bloc."; exit 3; }
case "$TGT" in *:*) : ;; *) ko "La clé Telegram n'a pas le bon format. Relance le bloc."; exit 3;; esac

say "3/6 Installation"
id l81watch >/dev/null 2>&1 || sudo useradd --system --home-dir /var/lib/legacis81-watch --shell /sbin/nologin l81watch
sudo install -d -m 750 -o l81watch -g l81watch /var/lib/legacis81-watch
sudo install -d -m 750 -o root -g l81watch /etc/legacis81
sudo install -d -m 755 /opt/legacis81/watch
sudo install -m 755 l81_watch.py /opt/legacis81/watch/l81_watch.py
umask 077
printf 'TG_TOKEN=%s\nGMAIL_USER=legacis81@gmail.com\nGMAIL_APP_PW=%s\nTG_CHAT_ID=0\n' "$TGT" "$GPW" | sudo tee /etc/legacis81/watch.env >/dev/null
unset TGT GPW
sudo chown root:l81watch /etc/legacis81/watch.env && sudo chmod 640 /etc/legacis81/watch.env
ok "Programme installé, codes rangés dans un fichier protégé"

RUN="sudo -u l81watch python3 /opt/legacis81/watch/l81_watch.py"
say "4/6 Liaison avec ton Telegram"
echo "Ouvre @Legacis81StudioBot dans Telegram et envoie : /start"
read -rp "Quand c'est envoyé, appuie sur Entrée ici… " _
CID=$($RUN chatid | python3 -c 'import sys,json; d=json.load(sys.stdin); print(list(d)[-1] if d else "")')
[ -n "$CID" ] || { ko "Aucun /start reçu par le bot. Envoie /start puis relance le bloc."; exit 4; }
sudo sed -i "s/^TG_CHAT_ID=.*/TG_CHAT_ID=$CID/" /etc/legacis81/watch.env
ok "Telegram relié"

say "5/6 Test complet"
$RUN selftest || { ko "Test échoué (code Gmail ou clé Telegram ?). Capture au RCO."; exit 5; }
ok "Message de test envoyé sur Telegram"

say "6/6 Activation automatique"
sudo tee /etc/systemd/system/l81-watch.service >/dev/null <<'EOF'
[Unit]
Description=LEGACIS81 surveillance Gmail -> Telegram
After=network-online.target
[Service]
Type=oneshot
User=l81watch
ExecStart=/usr/bin/python3 /opt/legacis81/watch/l81_watch.py run
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/legacis81-watch
PrivateTmp=yes
EOF
sudo tee /etc/systemd/system/l81-watch.timer >/dev/null <<'EOF'
[Unit]
Description=LEGACIS81 surveillance toutes les 5 minutes
[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Persistent=true
[Install]
WantedBy=timers.target
EOF
sudo tee /etc/systemd/system/l81-digest.service >/dev/null <<'EOF'
[Unit]
Description=LEGACIS81 résumé quotidien
[Service]
Type=oneshot
User=l81watch
ExecStart=/usr/bin/python3 /opt/legacis81/watch/l81_watch.py digest
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/legacis81-watch
EOF
sudo tee /etc/systemd/system/l81-digest.timer >/dev/null <<'EOF'
[Unit]
Description=LEGACIS81 résumé quotidien 19h UTC
[Timer]
OnCalendar=*-*-* 19:00:00 UTC
Persistent=true
[Install]
WantedBy=timers.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now l81-watch.timer l81-digest.timer
sudo systemctl start l81-watch.service; sleep 2
systemctl list-timers --no-pager | grep l81 || true
sudo journalctl -u l81-watch.service -n 5 --no-pager | tail -3
echo
ok "TERMINÉ. La surveillance tourne toute seule, même téléphone éteint."
echo "Dans Telegram, envoie /status à ton bot pour vérifier à tout moment."
