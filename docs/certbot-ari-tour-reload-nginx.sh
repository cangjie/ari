#!/bin/sh
set -eu
case "${RENEWED_LINEAGE:-}" in
    /etc/letsencrypt/live/tour.arimuseum.org)
        /usr/sbin/nginx -t
        /usr/bin/systemctl reload nginx
        ;;
esac
