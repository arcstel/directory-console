FROM debian:12-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      samba \
      samba-ad-dc \
      samba-ad-provision \
      samba-common-bin \
      smbclient \
      winbind \
      krb5-user \
      krb5-config \
      ldb-tools \
      ldap-utils \
      tdb-tools \
      acl \
      attr \
      dnsutils \
      procps \
      bash \
 && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY seed.sh /usr/local/bin/seed.sh
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/seed.sh

EXPOSE 53/tcp 53/udp 88 135 139 389 445 464 636 3268 3269

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
