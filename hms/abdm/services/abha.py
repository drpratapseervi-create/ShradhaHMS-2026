import requests
import base64
from .auth import abdm


class ABHAService:
    """
    ABDM M1 — Full V3 API Implementation
    ======================================
    ✅ Create ABHA via Aadhaar OTP
    ✅ Create ABHA via Driving License
    ✅ Create ABHA Address
    ✅ Download ABHA Card
    ✅ Verify ABHA Number / Address
    ✅ Verify by OTP / Mobile / Aadhaar
    ✅ New vs Returning Patient check
    ✅ Profile fetch and update

    Base URL: https://sandbox.abdm.gov.in/api  (V3 paths)
    Note: V1/V2 APIs are NOT accepted for M1 certification.
    """

    # ═══════════════════════════════════════════════════
    # SECTION 1 — GET PUBLIC CERTIFICATE (for encryption)
    # ═══════════════════════════════════════════════════

    @staticmethod
    def get_public_certificate() -> str:
        """
        Fetch ABDM RSA public key for encrypting Aadhaar/OTP.
        V3 endpoint: GET /v3/profile/public/certificate
        Returns PEM string.
        """
        r = requests.get(
            f"{abdm.BASE}/v3/profile/public/certificate",
            headers=abdm._headers(),
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        return (
            data.get("publicKey")
            or data.get("certificate")
            or r.text
        )

    @staticmethod
    def _encrypt(value: str) -> str:
        """
        RSA encrypt a value using ABDM public key.
        Algorithm: RSA/ECB/PKCS1Padding
        """
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import padding as rsa_padding

        pem_str = ABHAService.get_public_certificate()
        pem_str = pem_str.strip()

        if not pem_str.startswith("-----"):
            raise ValueError(f"Invalid PEM from ABDM: {pem_str[:80]}")

        public_key = serialization.load_pem_public_key(pem_str.encode())
        encrypted = public_key.encrypt(value.encode(), rsa_padding.PKCS1v15())
        return base64.b64encode(encrypted).decode()

    # ═══════════════════════════════════════════════════
    # SECTION 2 — CREATE ABHA VIA AADHAAR OTP (V3)
    # ═══════════════════════════════════════════════════

    @staticmethod
    def aadhaar_generate_otp(aadhaar: str) -> dict:
        """
        Step 1 — Send OTP to Aadhaar-registered mobile.
        V3: POST /v3/enrollment/request/otp
        """
        encrypted_aadhaar = ABHAService._encrypt(aadhaar)
        return abdm.post(
            "/v3/enrollment/request/otp",
            {
                "loginId": encrypted_aadhaar,
                "scope":   ["abha-enrol"],
                "loginHint": "aadhaar",
                "otpSystem": "aadhaar",
            }
        )

    @staticmethod
    def aadhaar_verify_otp(txn_id: str, otp: str) -> dict:
        """
        Step 2 — Verify OTP, get enrollment token.
        V3: POST /v3/enrollment/enrol/byAadhaar
        Returns: txnId, enrollmentNumber, tokens
        """
        encrypted_otp = ABHAService._encrypt(otp)
        return abdm.post(
            "/v3/enrollment/enrol/byAadhaar",
            {
                "authData": {
                    "authMethods": ["otp"],
                    "otp": {
                        "timeStamp": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
                        "txnId":     txn_id,
                        "otpValue":  encrypted_otp,
                    }
                },
                "consent": {
                    "code":    "abha-enrollment",
                    "version": "1.4",
                }
            }
        )

    # ═══════════════════════════════════════════════════
    # SECTION 3 — CREATE ABHA VIA DRIVING LICENSE (V3)
    # ═══════════════════════════════════════════════════

    @staticmethod
    def dl_generate_otp(mobile: str) -> dict:
        """
        Step 1 — Send OTP to mobile for DL-based enrollment.
        V3: POST /v3/enrollment/request/otp
        """
        return abdm.post(
            "/v3/enrollment/request/otp",
            {
                "loginId":   mobile,
                "scope":     ["abha-enrol"],
                "loginHint": "mobile",
                "otpSystem": "abdm",
            }
        )

    @staticmethod
    def dl_verify_otp(txn_id: str, otp: str) -> dict:
        """
        Step 2 — Verify mobile OTP for DL enrollment.
        V3: POST /v3/enrollment/request/otp/verify
        """
        encrypted_otp = ABHAService._encrypt(otp)
        return abdm.post(
            "/v3/enrollment/request/otp/verify",
            {
                "scope":   ["abha-enrol"],
                "txnId":   txn_id,
                "otp":     encrypted_otp,
                "otpSystem": "abdm",
            }
        )

    @staticmethod
    def dl_enroll(txn_id: str, dl_number: str, dob: str,
                  first_name: str, last_name: str, gender: str) -> dict:
        """
        Step 3 — Create ABHA using Driving License details.
        V3: POST /v3/enrollment/enrol/byDocument
        dob format: DD-MM-YYYY
        gender: M / F / O
        """
        return abdm.post(
            "/v3/enrollment/enrol/byDocument",
            {
                "txnId": txn_id,
                "documentType": "DRIVING_LICENCE",
                "documentId":   dl_number,
                "firstName":    first_name,
                "lastName":     last_name,
                "dob":          dob,
                "gender":       gender,
                "consent": {
                    "code":    "abha-enrollment",
                    "version": "1.4",
                }
            }
        )

    # ═══════════════════════════════════════════════════
    # SECTION 4 — CREATE ABHA ADDRESS (PHR Address)
    # ═══════════════════════════════════════════════════

    @staticmethod
    def create_abha_address(txn_id: str, abha_address: str, x_token: str) -> dict:
        """
        Create a PHR address (username@abdm) after ABHA number creation.
        V3: POST /v3/profile/account/abha-address
        x_token: token received after enrollment
        """
        return abdm.post(
            "/v3/profile/account/abha-address",
            {
                "txnId":       txn_id,
                "abhaAddress": abha_address,
                "preferred":   1,
            },
            extra_headers={"X-Token": f"Bearer {x_token}"}
        )

    @staticmethod
    def suggest_abha_address(x_token: str) -> dict:
        """
        Get suggested ABHA addresses for patient to choose from.
        V3: GET /v3/profile/account/abha-address/suggestions
        """
        return abdm.get(
            "/v3/profile/account/abha-address/suggestions",
            extra_headers={"X-Token": f"Bearer {x_token}"}
        )

    # ═══════════════════════════════════════════════════
    # SECTION 5 — DOWNLOAD ABHA CARD
    # ═══════════════════════════════════════════════════

    @staticmethod
    def download_abha_card_png(x_token: str) -> bytes:
        """
        Download ABHA card as PNG image.
        V3: GET /v3/profile/account/abha-card
        Returns raw PNG bytes.
        """
        r = requests.get(
            f"{abdm.BASE}/v3/profile/account/abha-card",
            headers={
                **abdm._headers(),
                "X-Token": f"Bearer {x_token}",
                "Accept":  "image/png",
            },
            timeout=15,
        )
        r.raise_for_status()
        return r.content

    @staticmethod
    def download_abha_card_pdf(x_token: str) -> bytes:
        """
        Download ABHA card as PDF.
        V3: GET /v3/profile/account/abha-card
        Returns raw PDF bytes.
        """
        r = requests.get(
            f"{abdm.BASE}/v3/profile/account/abha-card",
            headers={
                **abdm._headers(),
                "X-Token": f"Bearer {x_token}",
                "Accept":  "application/pdf",
            },
            timeout=15,
        )
        r.raise_for_status()
        return r.content

    # ═══════════════════════════════════════════════════
    # SECTION 6 — GET / UPDATE PROFILE
    # ═══════════════════════════════════════════════════

    @staticmethod
    def get_profile(x_token: str) -> dict:
        """
        Get full ABHA profile.
        V3: GET /v3/profile/account
        """
        return abdm.get(
            "/v3/profile/account",
            extra_headers={"X-Token": f"Bearer {x_token}"}
        )

    @staticmethod
    def update_profile(x_token: str, profile_data: dict) -> dict:
        """
        Update ABHA profile (name, address, email etc).
        V3: PUT /v3/profile/account
        profile_data keys: firstName, lastName, middleName,
                           email, address, pinCode, stateCode, districtCode
        """
        return abdm.post(
            "/v3/profile/account",
            profile_data,
            extra_headers={
                "X-Token": f"Bearer {x_token}",
                "X-HTTP-Method-Override": "PUT",
            }
        )

    # ═══════════════════════════════════════════════════
    # SECTION 7 — VERIFY ABHA (Returning Patient)
    # ═══════════════════════════════════════════════════

    @staticmethod
    def verify_send_otp(abha_id: str, scope: str = "abha-login") -> dict:
        """
        Send OTP to verify existing ABHA (returning patient).
        abha_id: ABHA number or ABHA address
        V3: POST /v3/profile/login/request/otp
        scope: abha-login | abha-enrol | link-token
        """
        return abdm.post(
            "/v3/profile/login/request/otp",
            {
                "loginId":   abha_id,
                "scope":     [scope],
                "loginHint": "abha-number",
                "otpSystem": "abdm",
            }
        )

    @staticmethod
    def verify_by_otp(txn_id: str, otp: str) -> dict:
        """
        Verify OTP for ABHA login/verification.
        V3: POST /v3/profile/login/verify
        Returns: token for further API calls
        """
        encrypted_otp = ABHAService._encrypt(otp)
        return abdm.post(
            "/v3/profile/login/verify",
            {
                "scope":   ["abha-login"],
                "txnId":   txn_id,
                "otp":     encrypted_otp,
                "otpSystem": "abdm",
            }
        )

    @staticmethod
    def verify_by_mobile(mobile: str) -> dict:
        """
        Verify patient by mobile number — send OTP.
        V3: POST /v3/profile/login/request/otp
        """
        return abdm.post(
            "/v3/profile/login/request/otp",
            {
                "loginId":   mobile,
                "scope":     ["abha-login"],
                "loginHint": "mobile",
                "otpSystem": "abdm",
            }
        )

    @staticmethod
    def verify_by_aadhaar(aadhaar: str) -> dict:
        """
        Verify patient by Aadhaar — send OTP.
        V3: POST /v3/profile/login/request/otp
        """
        encrypted = ABHAService._encrypt(aadhaar)
        return abdm.post(
            "/v3/profile/login/request/otp",
            {
                "loginId":   encrypted,
                "scope":     ["abha-login"],
                "loginHint": "aadhaar",
                "otpSystem": "aadhaar",
            }
        )

    @staticmethod
    def get_user_token(txn_id: str, x_token: str) -> dict:
        """
        Exchange txnId for a user token after OTP verify.
        V3: POST /v3/profile/login/verify/user
        """
        return abdm.post(
            "/v3/profile/login/verify/user",
            {"txnId": txn_id},
            extra_headers={"X-Token": f"Bearer {x_token}"}
        )

    # ═══════════════════════════════════════════════════
    # SECTION 8 — NEW vs RETURNING PATIENT CHECK
    # ═══════════════════════════════════════════════════

    @staticmethod
    def check_abha_exists(abha_number: str) -> dict:
        """
        Check if ABHA number exists — New vs Returning patient.
        V3: GET /v3/profile/account/{abhaNumber}/exists
        Returns: {'status': 'ACTIVE'} or 404
        """
        r = requests.get(
            f"{abdm.BASE}/v3/profile/account/{abha_number}/exists",
            headers=abdm._headers(),
            timeout=10,
        )
        if r.status_code == 404:
            return {"exists": False}
        r.raise_for_status()
        return {**r.json(), "exists": True}

    @staticmethod
    def search_by_health_id(abha_address: str) -> dict:
        """
        Search patient by ABHA address.
        V3: POST /v3/profile/login/request/otp  (with abha-address hint)
        """
        return abdm.post(
            "/v3/profile/login/request/otp",
            {
                "loginId":   abha_address,
                "scope":     ["abha-login"],
                "loginHint": "abha-address",
                "otpSystem": "abdm",
            }
        )

    # ═══════════════════════════════════════════════════
    # SECTION 9 — LINK EXISTING ABHA TO PATIENT RECORD
    # ═══════════════════════════════════════════════════

    @staticmethod
    def get_link_token(x_token: str) -> dict:
        """
        Get a link token after patient verification.
        Used for HIP-initiated linking (M2).
        V3: GET /v3/profile/link-token
        """
        return abdm.get(
            "/v3/profile/link-token",
            extra_headers={"X-Token": f"Bearer {x_token}"}
        )