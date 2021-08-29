# Let's Encrypt plugin for Heroku apps

A plugin for the certbot (Let's Encrypt) client that allows you to automate the installation, and most importantly the renewal, of SSL certificates for you Heroku apps.

## Heroku Automated Certificate Management (ACM)

If you are paying anything to Heroku for your app, you can use Heroku's ACM feature to automatically generate and renew Let's Encrypt certificates for your app.  
Ref: https://devcenter.heroku.com/articles/automated-certificate-management  

**This plugin is only useful if you somehow can't or don't want to use ACM. If so, continue below.**

## How to use

Requirements: [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli) and [certbot (or certbot-auto)](https://certbot.eff.org/) installed. You should run `heroku` at least once to make sure it's set-up correctly.

__1. Install the certbot-heroku plugin:__

Is your client called `certbot-auto`? See note 1 below.  
Did you install `certbot` on Mac using [Homebrew](http://brew.sh)? See note 2 below.

    $ curl -LO https://github.com/jeppeliisberg/certbot-heroku/archive/master.zip
    $ unzip master.zip && rm master.zip
    $ cd certbot-heroku-master
    $ pip install . # or `python setup.py install`

Note 1: Your LE client might be called `certbot-auto` instead of `certbot`.
If that is the case, use `~/.local/share/letsencrypt/bin/pip` or `~/.local/share/letsencrypt/bin/python` to install, instead of just `pip` or `python`.  
Also, you will need to re-install the plugin each time `certbot-auto` upgrades to a newer version, which it will do automatically unless you specify the `--no-self-upgrade` parameter when running `certbot-auto`.

Note 2: If you installed `certbot` using [Homebrew](http://brew.sh) on Mac, find the full path to the `python` binary using this command:

    cat $(which certbot) | head -1

Then use the full path to the `pip` binary found in the same folder to install.  
Also, you will need to re-install the plugin each time Homebrew will update `certbot`.

Did it work?

    $ certbot plugins
    [...]
    * certbot-heroku:heroku
    Description: Heroku SSL
    [...]

__2. Server-side:__  
In order for ACME authentication to succeed, you need to configure your Heroku app to answer the ACME challenge with the appropriate value.  

You will need and endpoint as follows:
{your-domain}/.well-known/acme-challenge(/:token)

Sending a POST request to this endpoint should create a challenge
Sending a DELETE request to the endpoint should remove the challenge (cleanup).
Sending a GET request with the appended token should provide the challenge in a plain text answer.

Here's a sample Rails implementation:

```
# config/routes.rb
post "/.well-known/acme-challenge", to: "content#create_certbot_validation"
get "/.well-known/acme-challenge/:token", to: "content#show_certbot_validation"
delete "/.well-known/acme-challenge", to: "content#destroy_certbot_validation"


# app/controllers/content_controller.rb
def create_certbot_validation
  authenticate_with_http_token do |token, _options|
    if token == ENV["CERTBOT_AUTHENTICATOR_TOKEN"]
      domain = Domain.find_by(full_domain: params[:domain])
      return head :not_found if domain.nil?
      token = params[:secret].split(".").first
      domain.update(certbot_token: token, certbot_validation: params[:secret])
      return head :ok
    else
      return head :unauthorized
    end
  end
end

def show_certbot_validation
  domain = Domain.find_by(certbot_token: params[:token])
  return head :not_found if domain.nil?
  render plain: domain.certbot_validation
end

def destroy_certbot_validation
  authenticate_with_http_token do |token, _options|
    if token == ENV["CERTBOT_AUTHENTICATOR_TOKEN"]
      domain = Domain.find_by(full_domain: params[:domain])
      return head :not_found if domain.nil?
      domain.update(certbot_token: nil, certbot_validation: nil)
      return head :ok
    else
      return head :unauthorized
    end
  end
end

```

__3. Usage:__

    $ certbot run --configurator heroku --heroku-app YourHerokuAppName --heroku-endpoint https://api.example.com/.well-known/acme-challenge --heroku-httptoken mysecrettoken -d www.example.com
      or
    $ certbot certonly --authenticator heroku --heroku-app YourHerokuAppName --heroku-endpoint https://api.example.com/.well-known/acme-challenge --heroku-httptoken mysecrettoken -d www.example.com
      or
    $ certbot install --installer heroku --heroku-app YourHerokuAppName -d www.example.com


## How it works

### Authentication
Before issuing a SSL certificate, the Certificate Authority (CA) needs to insure that you are the owner of the domain for which want the certificate.  
Let's Encrypt allows different protocols for doing so, but the one that is the easiest for most people is ACME.  
ACME is a protocol where the CA generates a random string, gives it to you, and asks you to put that string on your web server.  
On most servers, that would require simply dropping a text file at the right place on your web server, but with Heroku, that would require committing this file into git, and pushing to Heroku, before the CA could verify your ownership of the domain you are interested in.

This plugin provides an alternative by using your apps' API to store and answer the challenge.  
Some initial set-up is required, but once it's working, renewals can be automated very easily.

### Installer
Once the domain is authenticated, a new certificate is generated (by the Let's Encrypt CA), and is stored on your computer.

The plugin will take that certificate, and the associated key, and install those on your Heroku app.  
It does that using the `heroku certs` command ([ref](https://devcenter.heroku.com/articles/ssl)).
