# hms/dicom.py
import requests

ORTHANC_URL     = 'http://localhost:8042'
ORTHANC_USER    = 'orthanc'
ORTHANC_PASS    = 'orthanc'


def upload_dicom(dicom_bytes):
    """Upload a DICOM file to Orthanc — returns instance ID"""
    response = requests.post(
        f'{ORTHANC_URL}/instances',
        data=dicom_bytes,
        headers={'Content-Type': 'application/dicom'},
        auth=(ORTHANC_USER, ORTHANC_PASS)
    )
    if response.status_code == 200:
        return response.json().get('ID')
    return None


def get_dicom_preview(instance_id):
    """Get PNG preview of a DICOM image"""
    response = requests.get(
        f'{ORTHANC_URL}/instances/{instance_id}/preview',
        auth=(ORTHANC_USER, ORTHANC_PASS)
    )
    return response.content if response.status_code == 200 else None


def get_all_studies():
    """Get all studies from Orthanc"""
    response = requests.get(
        f'{ORTHANC_URL}/studies',
        auth=(ORTHANC_USER, ORTHANC_PASS)
    )
    return response.json() if response.status_code == 200 else []


def delete_instance(instance_id):
    """Delete a DICOM instance"""
    requests.delete(
        f'{ORTHANC_URL}/instances/{instance_id}',
        auth=(ORTHANC_USER, ORTHANC_PASS)
    )