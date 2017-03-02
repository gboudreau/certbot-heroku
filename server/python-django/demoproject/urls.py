from django.conf.urls import url
from django.contrib import admin
from demoproject.views import letsencrypt_challenge_response


urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'^\.well-known/acme-challenge/', letsencrypt_challenge_response),
]
