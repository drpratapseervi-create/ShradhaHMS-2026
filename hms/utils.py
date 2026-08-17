from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa

def render_to_pdf(template_src, context):
    template = get_template(template_src)
    html = template.render(context)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = "inline; filename=consultation.pdf"

    pisa.CreatePDF(html, dest=response)
    return response
