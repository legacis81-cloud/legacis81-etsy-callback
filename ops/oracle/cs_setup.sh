#!/bin/bash
# LEGACIS81 - à lancer dans Oracle Cloud Shell (réseau Public). Aucun secret ici.
# Ouvre l'accès au serveur A1 par le Bastion, copie le programme et lance l'installation.
set -u
BASE="https://raw.githubusercontent.com/legacis81-cloud/legacis81-etsy-callback/main/ops/oracle"
T=$OCI_TENANCY
echo "➜ Recherche du serveur et du Bastion…"
IID=$(oci compute instance list -c $T --all --query "data[?\"display-name\"=='legacis81-orchestrator-01' && \"lifecycle-state\"=='RUNNING'].id | [0]" --raw-output)
VNIC=$(oci compute vnic-attachment list -c $T --instance-id $IID --query 'data[0]."vnic-id"' --raw-output)
IP=$(oci network vnic get --vnic-id $VNIC --query 'data."private-ip"' --raw-output)
BID=$(oci bastion bastion list -c $T --all --query "data[?\"lifecycle-state\"=='ACTIVE'].id | [0]" --raw-output)
echo "  serveur $IP"
KEY=~/.ssh/legacis81_cloudshell_rsa
[ -f $KEY ] || { echo "✘ Clé Cloud Shell absente : capture au RCO"; exit 1; }
if timeout 8 bash -c "</dev/tcp/$IP/22" 2>/dev/null; then
  echo "✔ Réseau privé : accès direct au serveur"
  cat > ~/.ssh/config <<CFG
Host a1
  HostName $IP
  User opc
  IdentityFile $KEY
  IdentityFile ~/.ssh/legacis81_cloudshell_ecdsa
  StrictHostKeyChecking accept-new
  UserKnownHostsFile ~/.ssh/known_hosts_a1
CFG
  chmod 600 ~/.ssh/config
  DIRECT=1
else DIRECT=0; fi
if [ $DIRECT = 0 ]; then
if ! timeout 8 bash -c "</dev/tcp/host.bastion.uk-london-1.oci.oraclecloud.com/22" 2>/dev/null; then
  echo "✘ Cloud Shell est sur un réseau privé : en haut, Network → Public network, puis relance la commande."; exit 1; fi
echo "➜ Ouverture d'une session Bastion de 3 h (≈ 1 min)…"
SID=$(oci bastion session create-port-forwarding --bastion-id $BID --target-private-ip $IP --target-port 22 --ssh-public-key-file $KEY.pub --display-name LEG81-WATCH-$(date -u +%Y%m%d%H%M) --session-ttl 10800 --wait-for-state SUCCEEDED --query 'data.resources[0].identifier' --raw-output 2>/tmp/bsess.err)
[ -n "$SID" ] && [ "$SID" != "null" ] || { echo "✘ Session Bastion refusée :"; tail -5 /tmp/bsess.err; exit 1; }
pkill -f "L 2222:" 2>/dev/null
sleep 5
ssh -i $KEY -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -f -N -L 2222:$IP:22 -p 22 $SID@host.bastion.uk-london-1.oci.oraclecloud.com
sleep 3
cat > ~/.ssh/config <<CFG
Host a1
  HostName localhost
  Port 2222
  User opc
  IdentityFile $KEY
  IdentityFile ~/.ssh/legacis81_cloudshell_ecdsa
  StrictHostKeyChecking accept-new
  UserKnownHostsFile ~/.ssh/known_hosts_a1
CFG
chmod 600 ~/.ssh/config
fi
ssh -o ConnectTimeout=20 -o BatchMode=yes a1 'echo ok' >/tmp/a1.err 2>&1 || { echo "✘ Connexion au serveur impossible : capture au RCO"; tail -3 /tmp/a1.err; exit 1; }
echo "✔ Connecté au serveur"
D=$(mktemp -d)
for f in l81_watch.py install_a1.sh; do curl -fsSL "$BASE/$f" -o "$D/$f" || { echo "✘ Téléchargement $f"; exit 1; }; done
ssh a1 'mkdir -p ~/l81-install'
scp -q "$D/l81_watch.py" "$D/install_a1.sh" a1:l81-install/
ssh -t a1 'bash ~/l81-install/install_a1.sh'
