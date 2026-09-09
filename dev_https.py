"""
Local HTTPS dev server — for iPhone / LAN testing of features that need a
"secure context" (microphone, clipboard, etc.). NOT for production.

    .venv_new\\Scripts\\python.exe dev_https.py [host] [port]

Defaults to 0.0.0.0:8443  ->  https://<this-machine-LAN-IP>:8443

On first run it writes a self-signed cert (dev-cert.pem / dev-key.pem) next
to this file. Delete those two files to regenerate (e.g. after the LAN IP
changes). Serves the same Django app + WhiteNoise static as runserver; it
does NOT auto-reload, so restart it after code changes.
"""
import datetime
import ipaddress
import os
import socket
import ssl
import sys
from pathlib import Path
from socketserver import ThreadingMixIn

BASE = Path(__file__).resolve().parent
CERT = BASE / "dev-cert.pem"
KEY = BASE / "dev-key.pem"

HOST = sys.argv[1] if len(sys.argv) > 1 else "0.0.0.0"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8443


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def make_cert(ip):
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ip)])
    san = x509.SubjectAlternativeName([
        x509.IPAddress(ipaddress.ip_address(ip)),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        x509.DNSName("localhost"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(san, critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    KEY.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"Wrote self-signed cert for {ip}  ->  {CERT.name} / {KEY.name}")


def main():
    ip = lan_ip()
    if not CERT.exists() or not KEY.exists():
        make_cert(ip)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ShradhaHMS.settings")
    import django
    django.setup()
    from django.core.wsgi import get_wsgi_application
    from django.core.servers.basehttp import WSGIServer, WSGIRequestHandler

    class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
        daemon_threads = True

    httpd = ThreadingWSGIServer((HOST, PORT), WSGIRequestHandler)
    httpd.set_app(get_wsgi_application())

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(CERT), keyfile=str(KEY))
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)

    print(f"HTTPS dev server: https://{ip}:{PORT}/   (Ctrl+C to stop)")
    print("No auto-reload — restart after code changes.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
