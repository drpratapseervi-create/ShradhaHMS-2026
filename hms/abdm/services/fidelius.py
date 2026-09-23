"""
ABDM data-flow encryption ("Fidelius" protocol): ECDH key agreement on
the BouncyCastle "BC25519" curve + HKDF-SHA256 + AES-256-GCM.

ABDM's sandbox doc ("Encryption and Decryption Implementation Guidelines
for FHIR data in ABDM") only sketches this -- salt/IV come from XORing
the two parties' nonces, HKDF-SHA256 derives the AES key, AES-256-GCM
encrypts. The exact curve, HKDF info string, and key encoding aren't
spelled out there; they're taken from the reference Python port at
https://github.com/dimagi/pyfidelius (itself a port of the Java
fidelius-cli reference ABDM's docs point to), cross-checked here:

- BC25519 is Curve25519 re-expressed in short Weierstrass form (as
  fastecdsa's W25519), with its generator's y-coordinate swapped for
  BouncyCastle's own generator -- NOT the same curve as RFC 7748 X25519,
  so `cryptography`'s x25519 module can't be reused for the ECDH itself.
- fastecdsa (the reference impl's EC library) needs a C/GMP toolchain
  this project's Windows dev machine doesn't have, and pycryptodome
  isn't otherwise a dependency here -- so this module does BC25519's
  point arithmetic in pure Python (verified against pyfidelius's
  algorithm: generator-on-curve, ECDH symmetry, and order checks all
  pass) and reuses `cryptography` (already a dependency) for
  HKDF-SHA256 and AES-256-GCM, confirmed byte-for-byte identical to
  pycryptodome's HKDF/AES-GCM output for the same inputs.
- ABDM's `dhPublicKey.keyValue` on the wire is a BouncyCastle X.509
  SubjectPublicKeyInfo DER encoding of the EC public key, not a raw
  point -- `_X509_PREFIX` below is that fixed DER prefix (taken from
  the reference implementation) that the raw 32-byte X/Y coordinates
  get appended to.

Only HIP-side encryption is implemented (encrypt_content /
generate_key_material) -- this project never needs to decrypt ABDM
data, only send it.
"""

import base64
import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# BC25519 curve parameters (short Weierstrass form of Curve25519, with
# BouncyCastle's generator Y) -- see module docstring.
_P  = 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFED
_A  = 0x2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA984914A144
_B  = 0x7B425ED097B425ED097B425ED097B425ED097B425ED097B4260B5E9C7710C864
_N  = 0x1000000000000000000000000000000014DEF9DEA2F79CD65812631A5CF5D3ED
_GX = 0x2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD245A
_GY = 0x20AE19A1B8A086B4E01EDD2C7748D14C923D4D7E6D7C61B229E9C5A27ECED3D9
_G  = (_GX, _GY)

# BouncyCastle X.509 SubjectPublicKeyInfo DER prefix for BC25519 EC
# public keys. ABDM's keyMaterial.dhPublicKey.keyValue is this prefix
# followed by the raw 32-byte big-endian X and Y coordinates, all
# base64-encoded together.
_X509_PREFIX = base64.b64decode(
    "MIIBMTCB6gYHKoZIzj0CATCB3gIBATArBgcqhkjOPQEBAiB/////////////////////////////////////////7TBEBCAqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqYSRShRAQge0Je0Je0Je0Je0Je0Je0Je0Je0Je0Je0JgtenHcQyGQEQQQqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq0kWiCuGaG4oIa04B7dLHdI0UySPU1+bXxhsinpxaJ+ztPZAiAQAAAAAAAAAAAAAAAAAAAAFN753qL3nNZYEmMaXPXT7QIBCANCAAQ="
)


def _inv_mod(x, p):
    return pow(x, p - 2, p)


def _point_add(p1, p2):
    """Point addition/doubling on the short Weierstrass curve BC25519."""
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % _P == 0:
        return None  # point at infinity
    if x1 == x2 and y1 == y2:
        m = (3 * x1 * x1 + _A) * _inv_mod(2 * y1 % _P, _P) % _P
    else:
        m = (y2 - y1) * _inv_mod((x2 - x1) % _P, _P) % _P
    x3 = (m * m - x1 - x2) % _P
    y3 = (m * (x1 - x3) - y1) % _P
    return (x3, y3)


def _scalar_mult(k, point):
    result = None
    addend = point
    while k:
        if k & 1:
            result = _point_add(result, addend)
        addend = _point_add(addend, addend)
        k >>= 1
    return result


def _int_to_32bytes(n):
    return n.to_bytes(32, byteorder="big")


def generate_key_material():
    """
    Generate one ephemeral BC25519 key pair + a fresh 32-byte nonce for
    one ECDH exchange (one data-push transaction).
    Returns (private_key_b64, public_key_x509_b64, nonce_b64).
    """
    private_key = secrets.randbelow(_N - 1) + 1
    px, py = _scalar_mult(private_key, _G)

    private_key_b64 = base64.b64encode(_int_to_32bytes(private_key)).decode()
    public_key_x509_b64 = base64.b64encode(
        _X509_PREFIX + _int_to_32bytes(px) + _int_to_32bytes(py)
    ).decode()
    nonce_b64 = base64.b64encode(secrets.token_bytes(32)).decode()
    return private_key_b64, public_key_x509_b64, nonce_b64


def _decode_private_key(private_key_b64):
    return int.from_bytes(base64.b64decode(private_key_b64), "big")


def _decode_public_key(public_key_b64):
    raw = base64.b64decode(public_key_b64)
    if len(raw) == 65 and raw[0] == 0x04:
        # Raw uncompressed point: 0x04 || X(32) || Y(32)
        x_bytes, y_bytes = raw[1:33], raw[33:65]
    else:
        # X.509 SubjectPublicKeyInfo -- coordinates are the last 64 bytes
        x_bytes, y_bytes = raw[-64:-32], raw[-32:]
    return (int.from_bytes(x_bytes, "big"), int.from_bytes(y_bytes, "big"))


def _shared_secret_bytes(own_private_key_b64, other_public_key_b64):
    d = _decode_private_key(own_private_key_b64)
    other_point = _decode_public_key(other_public_key_b64)
    shared_point = _scalar_mult(d, other_point)
    return _int_to_32bytes(shared_point[0])


def encrypt_content(plaintext: str, sender_private_key_b64: str, sender_nonce_b64: str,
                     requester_public_key_b64: str, requester_nonce_b64: str) -> str:
    """
    Encrypt `plaintext` per ABDM's Fidelius data-flow encryption:
      xorOfNonces = senderNonce XOR requesterNonce   (both 32 bytes)
      IV   = xorOfNonces[-12:]
      salt = xorOfNonces[:20]
      sharedSecret = ECDH(senderPrivateKey, requesterPublicKey) on BC25519
      aesKey = HKDF-SHA256(sharedSecret, salt=salt, info=b"", length=32)
      output = base64(AES-256-GCM(aesKey, IV, plaintext) [ciphertext||tag])

    `sender_*` is this HIP's own ephemeral key material (see
    generate_key_material); `requester_*` is the HIU's key material as
    given in the health-information request's keyMaterial.

    NOTE: per the ABDM spec, one keyMaterial (and so one AES key + IV)
    covers an entire data-push transaction, not one entry -- callers
    encrypting multiple entries for the same push reuse the same
    sender/requester key material for all of them, which is the
    protocol's own design, not something introduced here.
    """
    sender_nonce = base64.b64decode(sender_nonce_b64)
    requester_nonce = base64.b64decode(requester_nonce_b64)
    xor_of_nonces = bytes(a ^ b for a, b in zip(sender_nonce, requester_nonce))
    iv = xor_of_nonces[-12:]
    salt = xor_of_nonces[:20]

    shared_secret = _shared_secret_bytes(sender_private_key_b64, requester_public_key_b64)
    aes_key = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=b"").derive(shared_secret)

    ciphertext_and_tag = AESGCM(aes_key).encrypt(iv, plaintext.encode("utf-8"), None)
    return base64.b64encode(ciphertext_and_tag).decode()
