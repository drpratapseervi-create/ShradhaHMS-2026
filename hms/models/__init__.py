from .core import Patient, Department, Doctor, atc_code_validator
from .opd import Appointment, ICDCode, Consultation, Prescription
from .catalog import (
    Symptom, Sign, PastHistory, SurgicalHistory, AdviceOption,
    DietAdviceOption, FollowUpNotePhrase, PrescriptionTemplate,
    PrescriptionTemplateItem, VillageMaster, DrugMaster,
)
from .lab import (
    InvestigationCategory, Investigation, InvestigationBill,
    InvestigationBillItem, InvestigationParameter, InvestigationResult,
)
from .imaging import MedicalImage, USGReport, USGImpressionOption
from .ipd import (
    Ward, Bed, BedStay, IPDAdmission, IPDVital, IPDMedication,
    IPDDischargeMedication, DischargeTemplate, IPDProgressNote,
    IPDSymptomHistory, IPDTreatmentHistory, IPDProcedure,
)
from .billing import (
    BillItem, PatientService, DischargeBill, DischargeBillItem,
    IPDAdvance, ProcedureItem, ProcedureBill, ProcedureBillItem,
)
from .accounts import UserProfile, Expense
from .abdm import (
    ABDMConsent, ABDMCareContext, ABDMLinkToken, ABDMLinkingSession,
    ABDMConsentRequest, ABDMConsentArtefact, ABDMHealthInformationRequest, ABDMReceivedRecord,
    ABDMScanShare,
)
from .ot import OTBooking, OTNotes
from .inventory import Supplier, InventoryItem, StockIn, StockOut, StockBatch
from .pharmacy import PharmacyBill, PharmacyBillItem, PharmacyReturn, PharmacyReturnItem
from .documents import (
    document_upload_path, HOSPITAL_DOC_TYPES, DOCTOR_DOC_TYPES,
    STAFF_DOC_TYPES, EQUIPMENT_DOC_TYPES, DOC_CATEGORY_CHOICES,
    ALL_DOC_TYPE_CHOICES, HospitalDocument,
)
from .construction import (
    EXPENSE_HEAD_CHOICES, AREA_CHOICES, PAYMENT_MODE_CHOICES,
    PAID_BY_CHOICES, PAID_FROM_CHOICES, APPROVAL_STATUS_CHOICES,
    APPROVED_BY_CHOICES, WORK_STATUS_CHOICES, YES_NO_PARTIAL_CHOICES,
    INVOICE_TYPE_CHOICES, REIMBURSED_CHOICES,
    CONSTRUCTION_MEDIA_VIDEO_EXTENSIONS, CONSTRUCTION_MEDIA_PHOTO_EXTENSIONS,
    CONSTRUCTION_MEDIA_DOCUMENT_EXTENSIONS, construction_media_upload_path,
    Vendor, ConstructionExpense, ConstructionMedia, PartnerPayment,
    ExpenseBudget, Partner, PartnerDeposit,
)
from .tpa import (
    TPA_SCHEME_TYPE_CHOICES, TPA_STATUS_CHOICES, TPA_DOCUMENT_TYPE_CHOICES,
    TPAScheme, TPAPatient, tpa_document_upload_path, TPADocument,
    TPAImportMapping, TPAImportBatch, TPAImportRow,
)

from auditlog.registry import auditlog

auditlog.register(Patient)
auditlog.register(Consultation)
auditlog.register(IPDAdmission)
auditlog.register(Prescription)
auditlog.register(InvestigationBill)
auditlog.register(InvestigationResult)
auditlog.register(DischargeBill)
auditlog.register(ICDCode)
auditlog.register(TPAPatient)
