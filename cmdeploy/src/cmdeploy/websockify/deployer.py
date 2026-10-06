from pyinfra.operations import apt, server

from cmdeploy.basedeploy import Deployer


class WebsockifyDeployer(Deployer):
    def __init__(self, config):
        self.config = config

    def install(self):
        apt.packages(name="Install websockify", packages=["websockify"])
        apt.packages(
            name="Install python3-websockets (DNS bridge)",
            packages=["python3-websockets"],
        )

    def configure(self):
        # Velta C3: both tunnels land on the TLS ports (993/465) — the wasm
        # core keeps TLS inside the wasm sandbox (design G), so the proxy
        # never terminates mail-layer TLS.
        self.ensure_systemd_unit("websockify/websockify-imap.service")
        self.ensure_systemd_unit("websockify/websockify-submission.service")
        self.ensure_systemd_unit(
            "websockify/websockify-dns.service.j2",
            mail_domain=self.config.mail_domain,
        )
        self.put_executable(
            "websockify/ws-dns-bridge.py",
            "/usr/local/lib/websockify/ws-dns-bridge.py",
        )

    def activate(self):
        self.ensure_service("websockify-imap.service")
        self.ensure_service("websockify-submission.service")
        self.ensure_service("websockify-dns.service")
