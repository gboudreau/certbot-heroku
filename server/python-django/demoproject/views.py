import os
from django.http import HttpResponse


def letsencrypt_challenge_response(request):
    return HttpResponse(
        os.getenv('LETS_ENCRYPT_CHALLENGE', 'not set'),
        content_type='text/plain'
    )
