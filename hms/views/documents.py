import os

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.db.models import Q
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from ..models import (
    HospitalDocument,
    HOSPITAL_DOC_TYPES, DOCTOR_DOC_TYPES, STAFF_DOC_TYPES, EQUIPMENT_DOC_TYPES,
)


@login_required
def document_dashboard(request):
    today = timezone.now().date()
    from datetime import timedelta

    all_docs = HospitalDocument.objects.all()

    expired       = [d for d in all_docs if d.expiry_status == 'expired']
    expiring_soon = [d for d in all_docs if d.expiry_status == 'expiring_soon']

    return render(request, 'documents/dashboard.html', {
        'total_docs':      all_docs.count(),
        'hospital_count':  all_docs.filter(category='hospital').count(),
        'doctor_count':    all_docs.filter(category='doctor').count(),
        'staff_count':     all_docs.filter(category='staff').count(),
        'equipment_count': all_docs.filter(category='equipment').count(),
        'expired_count':   len(expired),
        'expiring_count':  len(expiring_soon),
        'expired_docs':    expired[:5],
        'expiring_docs':   expiring_soon[:5],
        'recent_docs':     all_docs.order_by('-created_at')[:8],
        'doc_categories':  [
            ('hospital',  'Hospital'),
            ('doctor',    'Doctor'),
            ('staff',     'Staff'),
            ('equipment', 'Equipment AMC / Certificate'),
        ],
    })


@login_required
def document_list(request):
    category = request.GET.get('category', '')
    search   = request.GET.get('q', '').strip()
    status   = request.GET.get('status', '')

    docs = HospitalDocument.objects.all().order_by('category', 'expiry_date')

    if category:
        docs = docs.filter(category=category)
    if search:
        docs = docs.filter(
            Q(title__icontains=search) |
            Q(person_name__icontains=search) |
            Q(equipment_name__icontains=search) |
            Q(issued_by__icontains=search)
        )

    # Filter by expiry status (done in Python since it's a property)
    if status:
        docs = [d for d in docs if d.expiry_status == status]

    return render(request, 'documents/document_list.html', {
        'docs':              docs,
        'category':          category,
        'search':            search,
        'status':            status,
        'hospital_doc_types':  HOSPITAL_DOC_TYPES,
        'doctor_doc_types':    DOCTOR_DOC_TYPES,
        'staff_doc_types':     STAFF_DOC_TYPES,
        'equipment_doc_types': EQUIPMENT_DOC_TYPES,
    })


@login_required
def document_add(request):
    if request.method == 'POST':
        category       = request.POST.get('category')
        doc_type       = request.POST.get('doc_type')
        title          = request.POST.get('title', '').strip()
        person_name    = request.POST.get('person_name', '').strip()
        equipment_name = request.POST.get('equipment_name', '').strip()
        issued_by      = request.POST.get('issued_by', '').strip()
        issue_date     = request.POST.get('issue_date') or None
        expiry_date    = request.POST.get('expiry_date') or None
        notes          = request.POST.get('notes', '').strip()
        doc_file       = request.FILES.get('document_file')

        if not title or not category or not doc_type:
            messages.error(request, 'Category, Document Type and Title are required.')
        else:
            HospitalDocument.objects.create(
                category       = category,
                doc_type       = doc_type,
                title          = title,
                person_name    = person_name or None,
                equipment_name = equipment_name or None,
                issued_by      = issued_by or None,
                issue_date     = issue_date,
                expiry_date    = expiry_date,
                notes          = notes or None,
                document_file  = doc_file,
            )
            messages.success(request, f'Document "{title}" added successfully.')
            return redirect('hms:document_list')

    return render(request, 'documents/document_form.html', {
        'action':              'Add',
        'hospital_doc_types':  HOSPITAL_DOC_TYPES,
        'doctor_doc_types':    DOCTOR_DOC_TYPES,
        'staff_doc_types':     STAFF_DOC_TYPES,
        'equipment_doc_types': EQUIPMENT_DOC_TYPES,
        'category_pre':        request.GET.get('category', ''),
    })


@login_required
def document_edit(request, doc_id):
    doc = get_object_or_404(HospitalDocument, id=doc_id)

    if request.method == 'POST':
        doc.category       = request.POST.get('category')
        doc.doc_type       = request.POST.get('doc_type')
        doc.title          = request.POST.get('title', '').strip()
        doc.person_name    = request.POST.get('person_name', '').strip() or None
        doc.equipment_name = request.POST.get('equipment_name', '').strip() or None
        doc.issued_by      = request.POST.get('issued_by', '').strip() or None
        doc.issue_date     = request.POST.get('issue_date') or None
        doc.expiry_date    = request.POST.get('expiry_date') or None
        doc.notes          = request.POST.get('notes', '').strip() or None

        new_file = request.FILES.get('document_file')
        if new_file:
            doc.document_file = new_file

        doc.save()
        messages.success(request, f'Document "{doc.title}" updated successfully.')
        return redirect('hms:document_list')

    return render(request, 'documents/document_form.html', {
        'action':              'Edit',
        'doc':                 doc,
        'hospital_doc_types':  HOSPITAL_DOC_TYPES,
        'doctor_doc_types':    DOCTOR_DOC_TYPES,
        'staff_doc_types':     STAFF_DOC_TYPES,
        'equipment_doc_types': EQUIPMENT_DOC_TYPES,
    })


@login_required
def document_delete(request, doc_id):
    doc = get_object_or_404(HospitalDocument, id=doc_id)
    if request.method == 'POST':
        title = doc.title
        if doc.document_file:
            try:
                if os.path.isfile(doc.document_file.path):
                    os.remove(doc.document_file.path)
            except Exception:
                pass
        doc.delete()
        messages.success(request, f'Document "{title}" deleted.')
    return redirect('hms:document_list')


@login_required
def document_types_ajax(request):
    category = request.GET.get('category', '')
    type_map = {
        'hospital':  HOSPITAL_DOC_TYPES,
        'doctor':    DOCTOR_DOC_TYPES,
        'staff':     STAFF_DOC_TYPES,
        'equipment': EQUIPMENT_DOC_TYPES,
    }
    types = type_map.get(category, [])
    return JsonResponse({'types': [{'value': v, 'label': l} for v, l in types]})

