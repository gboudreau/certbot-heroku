# How to configure your Django Heroku app to answer ACME challenges using
# certbot-heroku

- __demoproject/views.py__ simple view that reads the `LETS_ENCRYPT_CHALLENGE`
  environment variable (Heroku config var), and outputs it.
- __demoprojects/urls.py__ set up route so that all requests to
  _/.well-known/acme-challenge/*_ are processed by the view in _views.py_
