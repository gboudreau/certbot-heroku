# How to configure your PHP-apache Heroku app to answer ACME challenges using certbot-heroku

- __htaccess__: place this file in /.well-known/acme-challenge/.htaccess; it will route all requests for /.well-known/acme-challenge/* to /acme-challenge.php;
- __acme-challenge.php__: read the `LETS_ENCRYPT_CHALLENGE` environment variable (Heroku config var), and outputs it.

Are you using another buildpack on Heroku, and created your own version of this? If so, please send me a Pull Request to document how you did it! Thanks.
