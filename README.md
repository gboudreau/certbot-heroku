# Let's Encrypt plugin for Heroku apps

A plugin for the certbot (Let's Encrypt) client that allows you to automate the installation, and most importantly the renewal, of SSL certificates for you Heroku apps.


## How to use

Requirements: [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli) and [certbot (or certbot-auto)](https://certbot.eff.org/) installed. You should run `heroku` at least once to make sure it's set-up correctly.

Note that the authorization plugin is not compatible with Heroku's [Preboot feature](https://devcenter.heroku.com/articles/preboot). If enabled for the specified app, it will be temporarily disabled to allow the plugin to do it's job.

__1. Install the certbot-heroku plugin:__

Is your client called `certbot-auto`? See note 1 below.  
Did you install `certbot` on Mac using [Homebrew](http://brew.sh)? See note 2 below.

    $ curl -LO https://github.com/gboudreau/certbot-heroku/archive/master.zip
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

__2. Server-side script:__  
In order for ACME authentication to succeed, you need to configure your Heroku app to answer the ACME challenge with the appropriate value (stored in the `LETS_ENCRYPT_CHALLENGE` environment variable).  
How you do that depends on the buildpack you use. See examples in the [server/](https://github.com/gboudreau/certbot-heroku/tree/master/server) folder.

__3. Usage:__

    $ certbot run --configurator certbot-heroku:heroku -H YourHerokuAppName -d www.example.com
      or
    $ certbot certonly --authenticator certbot-heroku:heroku -H YourHerokuAppName -d www.example.com
      or
    $ certbot install --installer certbot-heroku:heroku -H YourHerokuAppName -d www.example.com


## How it works

### Authentication
Before issuing a SSL certificate, the Certificate Authority (CA) needs to insure that you are the owner of the domain for which want the certificate.  
Let's Encrypt allows different protocols for doing so, but the one that is the easiest for most people is ACME.  
ACME is a protocol where the CA generates a random string, gives it to you, and asks you to put that string on your web server.  
On most servers, that would require simply dropping a text file at the right place on your web server, but with Heroku, that would require committing this file into git, and pushing to Heroku, before the CA could verify your ownership of the domain you are interested in.

This plugin simplify this by using an [Heroku config var](https://devcenter.heroku.com/articles/config-vars) (`LETS_ENCRYPT_CHALLENGE`) to store and answer the challenge.  
Some initial set-up is required, but once it's working, renewals can be automated very easily.

### Installer
Once the domain is authenticated, a new certificate is generated (by the Let's Encrypt CA), and is stored on your computer.

The plugin will take that certificate, and the associated key, and install those on your Heroku app.  
It does that using the `heroku certs` command ([ref](https://devcenter.heroku.com/articles/ssl)).
