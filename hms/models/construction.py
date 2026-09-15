import os
import re
from datetime import datetime
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator

# =====================================================================
# CONSTRUCTION EXPENSE MODELS
# =====================================================================

EXPENSE_HEAD_CHOICES = [
    # ── CIVIL & STRUCTURE ──
    ('Soil Removal / Excavation',  'Soil Removal / Excavation'),
    ('Soil Transport',             'Soil Transport'),
    ('PCC Work',                   'PCC Work'),
    ('RCC Work',                   'RCC Work'),
    ('Raft Foundation',            'Raft Foundation'),
    ('Brickwork / Masonry',        'Brickwork / Masonry'),
    ('Concrete / RMC',             'Concrete / RMC'),
    ('Shuttering / Formwork',      'Shuttering / Formwork'),
    ('Stone Work',                 'Stone Work'),
    ('Civil Work (General)',       'Civil Work (General)'),

    # ── RAW MATERIALS ──
    ('Cement',                     'Cement'),
    ('Steel / TMT Bars',           'Steel / TMT Bars'),
    ('Sand',                       'Sand'),
    ('Bricks',                     'Bricks'),
    ('Stone / Gitti / Aggregate',  'Stone / Gitti / Aggregate'),
    ('RMC (Ready Mix Concrete)',   'RMC (Ready Mix Concrete)'),
    ('Fly Ash',                    'Fly Ash'),
    ('Waterproofing Material',     'Waterproofing Material'),

    # ── FINISHING ──
    ('Tiles',                      'Tiles'),
    ('Granite / Marble',           'Granite / Marble'),
    ('Paint',                      'Paint'),
    ('Plaster Work',               'Plaster Work'),
    ('False Ceiling',              'False Ceiling'),
    ('POP / Gypsum Work',          'POP / Gypsum Work'),

    # ── SERVICES ──
    ('Electrical Work',            'Electrical Work'),
    ('Wiring & Conduit',           'Wiring & Conduit'),
    ('Electrical Fittings',        'Electrical Fittings'),
    ('Plumbing Work',              'Plumbing Work'),
    ('Plumbing Material',          'Plumbing Material'),
    ('AC Ducting / HVAC',          'AC Ducting / HVAC'),
    ('Fire Safety / Sprinkler',    'Fire Safety / Sprinkler'),
    ('Lift / Elevator',            'Lift / Elevator'),

    # ── DOORS, WINDOWS & FRAMES ──
    ('Doors',                      'Doors'),
    ('Windows',                    'Windows'),
    ('Aluminium / UPVC Work',      'Aluminium / UPVC Work'),
    ('Grills & Railings',          'Grills & Railings'),

    # ── FURNITURE & FIXTURES ──
    ('Furniture',                  'Furniture'),
    ('Modular Kitchen / Cabinets', 'Modular Kitchen / Cabinets'),
    ('Hospital Furniture',         'Hospital Furniture'),
    ('Curtains / Blinds',          'Curtains / Blinds'),

    # ── SPECIAL AREAS ──
    ('OT Construction',            'OT Construction'),
    ('Labour Room Construction',   'Labour Room Construction'),
    ('ICU Construction',           'ICU Construction'),
    ('Reception Work',             'Reception Work'),
    ('Ward Work',                  'Ward Work'),
    ('Pharmacy Setup',             'Pharmacy Setup'),
    ('Lab Setup',                  'Lab Setup'),

    # ── LABOUR ──
    ('Labour Charges',             'Labour Charges'),
    ('Mason / Mistri',             'Mason / Mistri'),
    ('Building Worker Expense',    'Building Worker Expense'),
    ('Contractor Payment',         'Contractor Payment'),

    # ── SALARY & STAFF ──
    ('Salary - Security Guard',    'Salary - Security Guard'),
    ('Salary - Site Supervisor',   'Salary - Site Supervisor'),
    ('Salary - Other Staff',       'Salary - Other Staff'),

    # ── TRANSPORT & EQUIPMENT ──
    ('Transport / Vehicle',        'Transport / Vehicle'),
    ('Equipment Rental',           'Equipment Rental'),
    ('Generator / Power',          'Generator / Power'),
    ('Crane / JCB / Machinery',    'Crane / JCB / Machinery'),

    # ── OTHER ──
    ('Government Fee / NOC',       'Government Fee / NOC'),
    ('Architect / Engineer Fee',   'Architect / Engineer Fee'),
    ('Site Office Expense',        'Site Office Expense'),
    ('Petrol / Diesel',            'Petrol / Diesel'),
    ('Misc / Other',               'Misc / Other'),
]
AREA_CHOICES = [
    # ── EXCAVATION & FOUNDATION ──
    ('Soil Removal / Excavation', 'Soil Removal / Excavation'),
    ('Raft Foundation',           'Raft Foundation'),
    ('PCC Work',                  'PCC Work'),
    ('RCC Work',                  'RCC Work'),
    ('Basement',                  'Basement'),
    # ── FLOORS ──
    ('Ground Floor',    'Ground Floor'),
    ('First Floor',     'First Floor'),
    ('Second Floor',    'Second Floor'),
    ('Third Floor',     'Third Floor'),
    ('Fourth Floor',    'Fourth Floor'),
    ('Terrace',         'Terrace'),
    ('Staircase',       'Staircase'),
    # ── HOSPITAL AREAS ──
    ('Reception',       'Reception'),
    ('OPD',             'OPD'),
    ('OT',              'OT'),
    ('Labour Room',     'Labour Room'),
    ('Ward',            'Ward'),
    ('Private Room',    'Private Room'),
    ('ICU',             'ICU'),
    ('Pharmacy',        'Pharmacy'),
    ('Lab',             'Lab'),
    ('X-Ray',           'X-Ray'),
    ('Toilet',          'Toilet'),
    ('Parking',         'Parking'),
    ('Front Elevation', 'Front Elevation'),
    ('General Building','General Building'),
]

PAYMENT_MODE_CHOICES = [
    ('Cash', 'Cash'),
    ('UPI', 'UPI'),
    ('Bank Transfer', 'Bank Transfer'),
    ('Cheque', 'Cheque'),
    ('Credit', 'Credit'),
]

PAID_BY_CHOICES = [
    ('Dr. Pratap Senecha', 'Dr. Pratap Senecha'),
    ('Mr. Lumbaram',       'Mr. Lumbaram'),
    ('Mr. Poonaram',       'Mr. Poonaram'),
    ('Company',            'Company'),
    ('Site Supervisor',    'Site Supervisor'),
]

PAID_FROM_CHOICES = [
    ('Personal', 'Personal'),
    ('Company', 'Company'),
    ('Cash Box', 'Cash Box'),
    ('Bank', 'Bank'),
]

APPROVAL_STATUS_CHOICES = [
    ('Pending', 'Pending'),
    ('Approved', 'Approved'),
    ('Rejected', 'Rejected'),
]

APPROVED_BY_CHOICES = [
    ('Dr. Pratap Senecha', 'Dr. Pratap Senecha'),
    ('Mr. Lumbaram',       'Mr. Lumbaram'),
    ('Mr. Poonaram',       'Mr. Poonaram'),
    ('All 3',              'All 3'),
]

WORK_STATUS_CHOICES = [
    ('Done', 'Done'),
    ('Pending', 'Pending'),
    ('Partial', 'Partial'),
]

YES_NO_PARTIAL_CHOICES = [
    ('Yes', 'Yes'),
    ('No', 'No'),
    ('Partial', 'Partial'),
]

INVOICE_TYPE_CHOICES = [
    ('Tax Invoice', 'Tax Invoice'),
    ('Estimate', 'Estimate'),
    ('Cash Memo', 'Cash Memo'),
    ('Quotation', 'Quotation'),
    ('NA', 'NA'),
]

REIMBURSED_CHOICES = [
    ('Yes', 'Yes'),
    ('No', 'No'),
    ('Pending', 'Pending'),
]


# ===================== VENDOR =====================

class Vendor(models.Model):
    name       = models.CharField(max_length=200)
    mobile     = models.CharField(max_length=20, blank=True, null=True)
    work_type  = models.CharField(max_length=100, blank=True, null=True)
    gst_no     = models.CharField(max_length=50, blank=True, null=True)
    address    = models.TextField(blank=True, null=True)
    notes      = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


# ===================== CONSTRUCTION EXPENSE =====================

class ConstructionExpense(models.Model):
    expense_id = models.CharField(max_length=20, unique=True, blank=True)

    date         = models.DateField(default=timezone.now)
    expense_head = models.CharField(max_length=100, choices=EXPENSE_HEAD_CHOICES)
    subcategory  = models.CharField(max_length=200, blank=True, null=True)
    description  = models.TextField()

    area_location = models.CharField(max_length=100, choices=AREA_CHOICES, blank=True, null=True)

    vendor        = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True)
    vendor_mobile = models.CharField(max_length=20, blank=True, null=True)
    bill_no       = models.CharField(max_length=100, blank=True, null=True)

    qty  = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    unit = models.CharField(max_length=50, blank=True, null=True)
    rate = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    amount       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gst_percent  = models.DecimalField(max_digits=5,  decimal_places=2, default=0)
    gst_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0, blank=True, null=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, blank=True, null=True)

    payment_mode = models.CharField(max_length=50, choices=PAYMENT_MODE_CHOICES, blank=True, null=True)
    paid_by      = models.CharField(max_length=50, choices=PAID_BY_CHOICES,      blank=True, null=True)
    paid_from    = models.CharField(max_length=50, choices=PAID_FROM_CHOICES,    blank=True, null=True)

    approval_status = models.CharField(max_length=20, choices=APPROVAL_STATUS_CHOICES, default='Pending')
    approved_by     = models.CharField(max_length=50, choices=APPROVED_BY_CHOICES, blank=True, null=True)

    work_status       = models.CharField(max_length=20, choices=WORK_STATUS_CHOICES,    blank=True, null=True)
    material_received = models.CharField(max_length=20, choices=YES_NO_PARTIAL_CHOICES, blank=True, null=True)

    invoice_type = models.CharField(max_length=50, choices=INVOICE_TYPE_CHOICES, blank=True, null=True)

    balance_due = models.DecimalField(max_digits=12, decimal_places=2, default=0, blank=True, null=True)
    due_date    = models.DateField(blank=True, null=True)

    remarks        = models.TextField(blank=True, null=True)
    bill_image     = models.ImageField(upload_to='construction_expenses/bills/',       blank=True, null=True)
    site_photo     = models.ImageField(upload_to='construction_expenses/site_photos/', blank=True, null=True)
    quotation_file = models.FileField(upload_to='construction_expenses/quotations/',   blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.expense_id:
            last_id = ConstructionExpense.objects.count() + 1
            self.expense_id = f"EXP-{last_id:04d}"
        if self.vendor and not self.vendor_mobile:
            self.vendor_mobile = self.vendor.mobile
        self.gst_amount   = (self.amount * self.gst_percent) / 100 if self.amount and self.gst_percent else 0
        self.total_amount = self.amount + self.gst_amount if self.amount else 0
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.expense_id} - {self.expense_head} - ₹{self.total_amount}"

    class Meta:
        ordering            = ['-created_at']
        verbose_name        = 'Construction Expense'
        verbose_name_plural = 'Construction Expenses'


# ===================== CONSTRUCTION MEDIA (PHOTOS, VIDEOS & DOCUMENTS) =====================

CONSTRUCTION_MEDIA_VIDEO_EXTENSIONS    = ['mp4', 'mov', 'avi', 'mkv', 'webm', '3gp']
CONSTRUCTION_MEDIA_PHOTO_EXTENSIONS    = ['jpg', 'jpeg', 'png', 'webp', 'heic']
CONSTRUCTION_MEDIA_DOCUMENT_EXTENSIONS = ['pdf', 'doc', 'docx', 'dwg', 'dxf']


def construction_media_upload_path(instance, filename):
    return f"construction_media/{timezone.now():%Y/%m}/{filename}"


class ConstructionMedia(models.Model):
    MEDIA_TYPE_CHOICES = [('video', 'Video'), ('photo', 'Photo'), ('document', 'Document')]

    file        = models.FileField(
        upload_to=construction_media_upload_path,
        validators=[FileExtensionValidator(
            allowed_extensions=(
                CONSTRUCTION_MEDIA_VIDEO_EXTENSIONS
                + CONSTRUCTION_MEDIA_PHOTO_EXTENSIONS
                + CONSTRUCTION_MEDIA_DOCUMENT_EXTENSIONS
            )
        )],
    )
    media_type  = models.CharField(max_length=10, choices=MEDIA_TYPE_CHOICES, blank=True)
    caption     = models.CharField(max_length=255, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.media_type and self.file:
            ext = self.file.name.rsplit('.', 1)[-1].lower()
            if ext in CONSTRUCTION_MEDIA_PHOTO_EXTENSIONS:
                self.media_type = 'photo'
            elif ext in CONSTRUCTION_MEDIA_DOCUMENT_EXTENSIONS:
                self.media_type = 'document'
            else:
                self.media_type = 'video'
        super().save(*args, **kwargs)

    def __str__(self):
        return self.caption or f"Construction {self.get_media_type_display()} {self.pk}"

    @property
    def filename(self):
        return os.path.basename(self.file.name)

    _FILENAME_DATE_RE = re.compile(r'(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})')

    @property
    def display_date(self):
        """The real capture date embedded in imported WhatsApp filenames
        (e.g. '...VIDEO-2026-05-29-09-40-36.mov'), falling back to
        uploaded_at for files that don't carry that pattern."""
        match = self._FILENAME_DATE_RE.search(self.filename)
        if match:
            year, month, day, hour, minute, second = (int(g) for g in match.groups())
            try:
                naive = datetime(year, month, day, hour, minute, second)
                return timezone.make_aware(naive, timezone.get_current_timezone())
            except ValueError:
                pass
        return self.uploaded_at

    @property
    def file_size_display(self):
        try:
            size = self.file.size
        except (OSError, ValueError):
            return ""
        size = float(size)
        for unit in ('B', 'KB', 'MB', 'GB'):
            if size < 1024 or unit == 'GB':
                return f"{size:.0f} {unit}" if unit == 'B' else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"

    class Meta:
        ordering            = ['-uploaded_at']
        verbose_name        = 'Construction Media'
        verbose_name_plural = 'Construction Media'


# ===================== PARTNER PAYMENT =====================

class PartnerPayment(models.Model):
    date         = models.DateField(default=timezone.now)
    partner_name = models.CharField(max_length=50, choices=PAID_BY_CHOICES)
    amount_paid  = models.DecimalField(max_digits=12, decimal_places=2)
    paid_for     = models.CharField(max_length=255)
    mode         = models.CharField(max_length=50, choices=PAYMENT_MODE_CHOICES, blank=True, null=True)
    expense_ref  = models.ForeignKey(ConstructionExpense, on_delete=models.SET_NULL, blank=True, null=True)
    reimbursed   = models.CharField(max_length=20, choices=REIMBURSED_CHOICES, default='No')
    remarks      = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.partner_name} - ₹{self.amount_paid}"

    class Meta:
        ordering = ['-date']


# ===================== EXPENSE BUDGET =====================

class ExpenseBudget(models.Model):
    expense_head  = models.CharField(max_length=100, choices=EXPENSE_HEAD_CHOICES, unique=True)
    budget_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def actual_spent(self):
        return ConstructionExpense.objects.filter(
            expense_head=self.expense_head
        ).aggregate(total=models.Sum('total_amount'))['total'] or 0

    def difference(self):
        return self.budget_amount - self.actual_spent()

    def status(self):
        return "Within Budget" if self.difference() >= 0 else "Over Budget"

    def __str__(self):
        return f"{self.expense_head} - Budget ₹{self.budget_amount}"

    class Meta:
        verbose_name        = 'Expense Budget'
        verbose_name_plural = 'Expense Budgets'
class Partner(models.Model):
    name = models.CharField(max_length=100)
    share_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    def __str__(self):
        return self.name


class PartnerDeposit(models.Model):
    TRANSACTION_TYPE = [
        ('deposit', 'Deposit'),
        ('withdraw', 'Withdraw'),
    ]
    partner = models.ForeignKey(Partner, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE, default='deposit')
    date = models.DateField()
    note = models.CharField(max_length=200, blank=True)
    voucher_no = models.CharField(max_length=50, unique=True, blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    added_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.partner.name} Rs {self.amount} ({self.transaction_type}) on {self.date}"

