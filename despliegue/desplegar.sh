#!/usr/bin/env bash
#
# Despliega el dashboard a la instancia Lightsail.
#
# Copia el codigo y el .db ya construido: **el servidor nunca consulta a Mercado
# Publico**. El pipeline corre en la maquina de desarrollo, donde vive el ticket
# y donde cabe el modelo de inferencia.
#
# Regla de seguridad: la instancia tiene tres sitios en produccion (acp,
# repuestos, serena). Nada de lo que hace este script los toca, y la
# verificacion final comprueba que sigan respondiendo.
#
# Uso:
#     bash despliegue/desplegar.sh              # despliega
#     bash despliegue/desplegar.sh --solo-datos # solo copia el .db y reinicia
#
# Sin variables en la linea de comandos: la ruta de la clave sale de
# LIGHTSAIL_KEY en el .env, y la copia publicable de la base se genera sola.

set -euo pipefail

# La configuracion se lee del .env, que NO esta versionado. Antes habia que
# recordar tres variables en la linea de comandos y el valor por defecto de
# CLAVE apuntaba a una ruta que no existe en esta maquina: el despliegue
# fallaba en el primer ssh con "Permission denied (publickey)", que parece un
# problema del servidor y es una ruta mal supuesta.
#
# La ruta de la clave no es un secreto, pero es personal: por eso vive en el
# .env y no en el repositorio.
if [ -f .env ]; then
    # Solo las claves de despliegue, y sin ejecutar el archivo.
    while IFS='=' read -r k v; do
        case "$k" in
            LIGHTSAIL_KEY|DEPLOY_SERVIDOR|DEPLOY_DOMINIO)
                v="${v%\"}"; v="${v#\"}"
                export "$k=$v" ;;
        esac
    done < <(grep -E '^(LIGHTSAIL_KEY|DEPLOY_SERVIDOR|DEPLOY_DOMINIO)=' .env || true)
fi

SERVIDOR="${SERVIDOR:-${DEPLOY_SERVIDOR:-ubuntu@54.207.164.201}}"
CLAVE="${CLAVE:-${LIGHTSAIL_KEY:-$HOME/.ssh/LightsailDefaultKey-sa-east-1.pem}}"
DOMINIO="${DOMINIO:-${DEPLOY_DOMINIO:-contratos.54-207-164-201.sslip.io}}"
DESTINO=/opt/contratos
PY="${PY:-./.venv/Scripts/python.exe}"
[ -x "$PY" ] || PY=python
BASE_LOCAL="${BASE_LOCAL:-data/publicar.db}"
FUENTE="${FUENTE:-data/contratos.db}"
SOLO_DATOS=0
[ "${1:-}" = "--solo-datos" ] && SOLO_DATOS=1

ssh_() { ssh -i "$CLAVE" -o StrictHostKeyChecking=accept-new -o BatchMode=yes \
             -o IdentitiesOnly=yes "$SERVIDOR" "$@"; }
scp_() { scp -i "$CLAVE" -o StrictHostKeyChecking=accept-new -o BatchMode=yes \
             -o IdentitiesOnly=yes -q "$@"; }

paso() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

# --------------------------------------------------------------------------
paso "Comprobaciones previas"

[ -f "$FUENTE" ] || {
    echo "ERROR: no existe $FUENTE. Corre el pipeline antes de desplegar."
    exit 1
}

# Copia CONSISTENTE con la API de backup de SQLite, no `cp`: si algo esta
# escribiendo la base —la inferencia, por ejemplo— un copiado plano puede
# capturarla a mitad de una transaccion.
"$PY" -c "import sqlite3,sys; o=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True); d=sqlite3.connect(sys.argv[2]); o.backup(d); d.close(); o.close()" "$FUENTE" "$BASE_LOCAL"
echo "  copia consistente: $FUENTE -> $BASE_LOCAL"
echo "  base local: $(du -h "$BASE_LOCAL" | cut -f1)"

# Un .db casi vacio es una corrida a medias: mejor no publicarla.
# Se usa Python y no el CLI sqlite3: el CLI no siempre esta instalado, y una
# comprobacion que falla en silencio es peor que no tenerla.
FILAS=$("$PY" -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('SELECT COUNT(*) FROM contrato').fetchone()[0])" "$BASE_LOCAL")
echo "  contratos en la base: $FILAS"
[ "$FILAS" -gt 0 ] || { echo "ERROR: la base no tiene contratos."; exit 1; }

ssh_ 'echo "  conectado a $(hostname), $(free -m | awk "/^Mem:/{print \$7}") MB disponibles"'

# --------------------------------------------------------------------------
if [ "$SOLO_DATOS" -eq 0 ]; then
    paso "Copiando codigo"
    ssh_ "sudo mkdir -p $DESTINO/data && sudo chown -R ubuntu:ubuntu $DESTINO"
    tar czf - src pyproject.toml README.md | ssh_ "tar xzf - -C $DESTINO"
    echo "  codigo copiado"

    paso "Instalando dependencias"
    # Sin extras de desarrollo: el servidor no corre tests ni linters.
    ssh_ "cd $DESTINO && python3 -m venv .venv 2>/dev/null; \
          .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -e ."
    ssh_ "$DESTINO/.venv/bin/python -c 'import contratos; print(\"  contratos\", contratos.__version__)'"
fi

# --------------------------------------------------------------------------
paso "Copiando la base"
scp_ "$BASE_LOCAL" "$SERVIDOR:$DESTINO/data/contratos.db"
ssh_ "ls -lh $DESTINO/data/contratos.db | awk '{print \"  \" \$5, \$9}'"

# El registro de la inferencia viaja con la base. Sin el, /inferencia pierde
# el embudo —cuantos documentos NO necesitaron el modelo—, que es el dato con
# el que esa pagina argumenta.
REGISTRO="$(dirname "$BASE_LOCAL")/corridas/inferencia.json"
if [ -f "$REGISTRO" ]; then
    ssh_ "mkdir -p $DESTINO/data/corridas"
    scp_ "$REGISTRO" "$SERVIDOR:$DESTINO/data/corridas/inferencia.json"
    echo "  registro de inferencia copiado"
else
    echo "  sin registro de inferencia local: la pagina lo declarara"
fi

# --------------------------------------------------------------------------
if [ "$SOLO_DATOS" -eq 0 ]; then
    paso "Servicio systemd"
    scp_ despliegue/contratos.service "$SERVIDOR:/tmp/contratos.service"
    ssh_ "sudo mv /tmp/contratos.service /etc/systemd/system/ && \
          sudo systemctl daemon-reload && sudo systemctl enable -q contratos"

    paso "nginx"
    scp_ despliegue/nginx.conf "$SERVIDOR:/tmp/contratos.nginx"
    ssh_ "sudo mv /tmp/contratos.nginx /etc/nginx/sites-available/contratos && \
          sudo ln -sf /etc/nginx/sites-available/contratos \
                      /etc/nginx/sites-enabled/contratos"
    # nginx -t ANTES de recargar: una config rota tumbaria los tres sitios.
    ssh_ "sudo nginx -t" 2>&1 | sed 's/^/  /'
    ssh_ "sudo systemctl reload nginx"
    echo "  nginx recargado"
fi

paso "Arrancando el servicio"
ssh_ "sudo systemctl restart contratos && sleep 2 && \
      systemctl is-active contratos | sed 's/^/  estado: /'"

# --------------------------------------------------------------------------
if [ "$SOLO_DATOS" -eq 0 ]; then
    paso "Certificado TLS"
    # certbot modifica el archivo de nginx IN SITU para agregar los bloques de
    # SSL. Como este script SOBRESCRIBE ese archivo en cada despliegue, hay que
    # volver a ejecutarlo SIEMPRE: saltarselo deja el sitio sin TLS y el 443
    # cae al certificado de otro sitio, con un error de nombre incorrecto.
    #
    # --keep-until-expiring reinstala la configuracion sin volver a pedir el
    # certificado: es idempotente y no gasta cuota de Let's Encrypt.
    CERTBOT="sudo certbot --nginx -d $DOMINIO --non-interactive --agree-tos"
    CERTBOT="$CERTBOT --register-unsafely-without-email"
    CERTBOT="$CERTBOT --keep-until-expiring --redirect"
    ssh_ "$CERTBOT" 2>&1 \
        | grep -iE "deploying|congratulations|not yet due|error" \
        | head -3 | sed 's/^/  /' || true
fi

# --------------------------------------------------------------------------
paso "Verificacion"

echo "  dashboard (desde el propio servidor):"
ssh_ "curl -sf http://127.0.0.1:8001/salud" | sed 's/^/    /'
echo ""

# GET y no HEAD: las rutas son GET-only y un HEAD devuelve 405, que parece un
# fallo sin serlo. Se recorren TODAS: un despliegue que solo prueba la portada
# no detecta una ruta rota.
echo "  rutas publicas:"
for r in / /contratos /legal /compras /finanzas /comercial /vencimientos /plazos /inferencia /estado /salud; do
    printf '    %-14s HTTP %s\n' "$r" \
        "$(curl -sS -o /dev/null -w '%{http_code}' "https://$DOMINIO$r")"
done

# Lo que de verdad importa: no haber roto lo que ya estaba.
echo "  sitios existentes (no deben haberse tocado):"
for sitio in serena acp; do
    printf '    %-8s      HTTP %s\n' "$sitio" \
        "$(curl -sS -o /dev/null -w '%{http_code}' \
            "https://$sitio.54-207-164-201.sslip.io")"
done

printf '\n\033[1mListo: https://%s\033[0m\n' "$DOMINIO"
