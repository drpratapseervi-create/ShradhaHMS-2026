import json

from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

from ..decorators import role_required
from ..models import (
    Symptom, Sign, PastHistory, SurgicalHistory,
    AdviceOption, DietAdviceOption,
    PrescriptionTemplate, PrescriptionTemplateItem,
)


@login_required
def save_prescription_template(request):
    if request.method != 'POST': 
        return JsonResponse({'error': 'POST required'}, status=405)
    import json
    data      = json.loads(request.body)
    name      = data.get('name', '').strip()
    medicines = data.get('medicines', [])
    if not name or not medicines:
        return JsonResponse({'error': 'Name and medicines required'}, status=400)
    template, created = PrescriptionTemplate.objects.get_or_create(name=name)
    template.created_by = request.user
    template.save()
    template.items.all().delete()
    for i, m in enumerate(medicines):
        PrescriptionTemplateItem.objects.create(
            template=template, medicine=m.get('medicine',''),
            dose=m.get('dose',''), frequency=m.get('frequency',''),
            duration=m.get('duration',''), instructions=m.get('instructions',''),
            order=i
        )
    return JsonResponse({'success': True, 'id': template.pk, 'name': template.name, 'created': created})


@login_required
def list_prescription_templates(request):
    templates = PrescriptionTemplate.objects.all().order_by('-created_at')
    return JsonResponse({'templates': [{'id': t.pk, 'name': t.name} for t in templates]})


@login_required
def load_prescription_template(request, pk):
    try:
        tpl = PrescriptionTemplate.objects.get(pk=pk)
        items = tpl.items.all()
        return JsonResponse({
            'id': tpl.id,
            'name': tpl.name,
            'items': [
                {
                    'medicine': item.medicine,
                    'dose': item.dose,
                    'frequency': item.frequency,
                    'duration': item.duration,
                    'instructions': item.instructions,
                }
                for item in items
            ],
        })
    except PrescriptionTemplate.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)


@login_required
def delete_prescription_template(request, pk):
    try:
        PrescriptionTemplate.objects.get(pk=pk).delete()
        return JsonResponse({'success': True})
    except PrescriptionTemplate.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)


@login_required
@role_required("doctor", "admin")
def add_symptom(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    data = json.loads(request.body)
    name = data.get('name', '').strip()
    dept_id = data.get('department_id')

    if not name:
        return JsonResponse({'error': 'Name required'}, status=400)

    sym, created = Symptom.objects.get_or_create(
        name=name,
        department_id=dept_id,
        defaults={'is_active': True}
    )

    return JsonResponse({'id': sym.id, 'name': sym.name, 'created': created})


@login_required
@role_required("doctor", "admin")
def delete_symptom(request, pk):
    try:
        Symptom.objects.get(pk=pk).delete()
        return JsonResponse({'success': True})
    except Symptom.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)


@login_required
@role_required("doctor", "admin")
def add_sign(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    data = json.loads(request.body)
    name = data.get('name', '').strip()
    dept_id = data.get('department_id')

    if not name:
        return JsonResponse({'error': 'Name required'}, status=400)

    sign, created = Sign.objects.get_or_create(
        name=name,
        department_id=dept_id,
        defaults={'is_active': True}
    )

    return JsonResponse({'id': sign.id, 'name': sign.name, 'created': created})


@login_required
@role_required("doctor", "admin")
def delete_sign(request, pk):
    try:
        Sign.objects.get(pk=pk).delete()
        return JsonResponse({'success': True})
    except Sign.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)


@login_required
@role_required("doctor", "admin")
def add_past_history(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    data = json.loads(request.body)
    name = data.get('name', '').strip()

    if not name:
        return JsonResponse({'error': 'Name required'}, status=400)

    item, created = PastHistory.objects.get_or_create(
        name=name,
        defaults={'is_active': True}
    )

    return JsonResponse({'id': item.id, 'name': item.name, 'created': created})


@login_required
@role_required("doctor", "admin")
def delete_past_history(request, pk):
    try:
        PastHistory.objects.get(pk=pk).delete()
        return JsonResponse({'success': True})
    except PastHistory.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)


@login_required
@role_required("doctor", "admin")
def add_surgical_history(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    data = json.loads(request.body)
    name = data.get('name', '').strip()

    if not name:
        return JsonResponse({'error': 'Name required'}, status=400)

    item, created = SurgicalHistory.objects.get_or_create(
        name=name,
        defaults={'is_active': True}
    )

    return JsonResponse({'id': item.id, 'name': item.name, 'created': created})


@login_required
@role_required("doctor", "admin")
def delete_surgical_history(request, pk):
    try:
        SurgicalHistory.objects.get(pk=pk).delete()
        return JsonResponse({'success': True})
    except SurgicalHistory.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)


@login_required
@role_required("doctor", "admin")
def add_advice_option(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    data = json.loads(request.body)
    text = data.get('text', '').strip()

    if not text:
        return JsonResponse({'error': 'Text required'}, status=400)

    item, created = AdviceOption.objects.get_or_create(
        text=text,
        defaults={'is_active': True}
    )

    return JsonResponse({'id': item.id, 'text': item.text, 'created': created})


@login_required
@role_required("doctor", "admin")
def delete_advice_option(request, pk):
    try:
        AdviceOption.objects.get(pk=pk).delete()
        return JsonResponse({'success': True})
    except AdviceOption.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)


@login_required
@role_required("doctor", "admin")
def add_diet_option(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    data = json.loads(request.body)
    text = data.get('text', '').strip()

    if not text:
        return JsonResponse({'error': 'Text required'}, status=400)

    item, created = DietAdviceOption.objects.get_or_create(
        text=text,
        defaults={'is_active': True}
    )

    return JsonResponse({'id': item.id, 'text': item.text, 'created': created})


@login_required
@role_required("doctor", "admin")
def delete_diet_option(request, pk):
    try:
        DietAdviceOption.objects.get(pk=pk).delete()
        return JsonResponse({'success': True})
    except DietAdviceOption.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

