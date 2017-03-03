import os
from flask import Flask

app = Flask(__name__)

@app.route('/.well-known/acme-challenge/<string:acmeChallenge>')
def letsencrypt_challenge_response(acmeChallenge):
    return (
        os.environ.get('LETS_ENCRYPT_CHALLENGE', 'not set')
    )
