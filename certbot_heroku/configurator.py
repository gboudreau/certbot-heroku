"""Heroku plugin."""
import argparse
import collections
import json
import logging
import os
import requests
import subprocess
import time

from acme import challenges

from certbot import errors
from certbot import interfaces
from certbot.display import util as display_util
from certbot.compat import os
from certbot.plugins import common


logger = logging.getLogger(__name__)

DEV_NULL = open(os.devnull, 'w')


class HerokuConfigurator(common.Installer, interfaces.Authenticator):
    """Heroku configurator."""

    description = "Heroku SSL"

    MORE_INFO = """\
Plugin that performs hostname validation using a REST API, then installs the generated certificate with
Heroku SSL. It expects that the Heroku CLI is already installed
and functional. See https://github.com/jeppeliisberg/certbot-heroku for
detailed set-up instructions."""

    def more_info(self):  # pylint: disable=missing-docstring,no-self-use
        return self.MORE_INFO

    @classmethod
    def add_parser_arguments(cls, add):
        add("app", default="", #action=_HerokuAppAction,
            help="The name of your Heroku app. This can be specified multiple "
                 "times to handle different domains; each domain will use "
                 "the Heroku app that preceded it.  For instance: `-H "
                 "MyApp -d example.com -d www.example.com -H "
                 "MyAppDev -d dev.example.com` (default: Ask)")
        add("endpoint", default="",
            help="The URL of the HTTP REST API used to set and remove ACME challenges")
        add("http-token", default="",
            help="The HTTP authentication token for the HTTP REST API used to set and remove ACME challenges")
        add("cert-name", default="",
            help="The Heroku certificate name (eg. 'tyrannosaurs-12345')")

    def get_chall_pref(self, domain):  # pragma: no cover
        # pylint: disable=missing-docstring,no-self-use,unused-argument
        return [challenges.HTTP01]

    def __init__(self, *args, **kwargs):
        super(HerokuConfigurator, self).__init__(*args, **kwargs)
        self.performed = collections.defaultdict(set)

    def prepare(self):  # pylint: disable=missing-docstring
        pass

    def perform(self, achalls):  # pylint: disable=missing-docstring
        domains = []
        for achall in achalls:
            domains.append(achall.domain)

        return [self._perform_single(achall) for achall in achalls]

    def _perform_single(self, achall):
        response, validation = achall.response_and_validation()
        heroku_app = self.conf("app")
        logger.info("Using the Heroku app %s for domain %s", heroku_app, achall.domain)

        try:
            # Check if we need to add the custom domain to the Heroku app
            ps = subprocess.Popen([_get_heroku_cli(), "domains", "-a", heroku_app], stdout=subprocess.PIPE)
            subprocess.check_call(['grep', achall.domain], stdin=ps.stdout, stdout=DEV_NULL)
            ps.wait()
        except subprocess.CalledProcessError:
            # Need to add domain to Heroku app
            subprocess.call([_get_heroku_cli(), "domains:add", achall.domain, "-a", heroku_app], stdout=DEV_NULL)

            ps = subprocess.Popen([_get_heroku_cli(), "domains", "-a", heroku_app], stdout=subprocess.PIPE)
            output = subprocess.check_output(['grep', achall.domain], stdin=ps.stdout)
            ps.wait()

            dns_host = output.decode("utf-8").replace("{0}  ".format(achall.domain), "").strip()
            raise errors.PluginError(
                "Error: Domain {0} was missing from Heroku app {1} custom domains.\n"
                "It was added, but you will need to update your DNS configuration to "
                "add a CNAME for {0} that points to {2}".format(achall.domain, heroku_app, dns_host))

        logger.info("  Sending ACME challenge response to REST API at '%s'", self.conf("endpoint"))
        r = requests.post(
            self.conf("endpoint"),
            data=json.dumps({"domain": achall.domain, "secret": validation}),
            headers={"Content-Type": "application/json", "Authorization": "Token {0}".format(self.conf("http-token"))},
        )
        logger.info(r.status_code)
        self.performed[heroku_app].add(achall)

        return response

    def cleanup(self, achalls):  # pylint: disable=missing-docstring
        for achall in achalls:
            # heroku_app = self.conf("map")[achall.domain]
            heroku_app = self.conf("app")
            logger.info("Clearing ACME challenge response from '%s'", heroku_app)
            r = requests.delete(
                self.conf("endpoint"),
                data=json.dumps({"domain": achall.domain}),
                headers={"Content-Type": "application/json", "Authorization": "Token {0}".format(self.conf("http-token"))},
            )

    #####
    # Installer
    #####

    # Entry point in main.py for installing cert
    def deploy_cert(self, domain, cert_path, key_path, chain_path=None, fullchain_path=None):
        # pylint: disable=unused-argument

        heroku_app = self.conf("app")
        heroku_cert_name = self.conf("cert-name")

        logger.info("Deploying certificate to Heroku app %s for domain %s", heroku_app, domain)

        try:
            # Check if we need to add the custom domain to the Heroku app
            ps = subprocess.Popen([_get_heroku_cli(), "domains", "-a", heroku_app], stdout=subprocess.PIPE)
            subprocess.check_call(['grep', domain], stdin=ps.stdout, stdout=DEV_NULL)
            ps.wait()
        except subprocess.CalledProcessError:
            # Need to add domain to Heroku app
            logger.info("Adding domain %s to Heroku app %s", domain, heroku_app)
            subprocess.call([_get_heroku_cli(), "domains:add", domain, "-a", heroku_app], stdout=DEV_NULL)

        try:
            # Check if we need to add or update the SSL cert
            ps = subprocess.Popen([_get_heroku_cli(), "certs", "-a", heroku_app], stdout=subprocess.PIPE)
            subprocess.check_call(['grep', domain], stdin=ps.stdout, stdout=DEV_NULL)
            ps.wait()

            # Cert found; i.e. need to update
            logger.info("Updating existing Heroku SSL endpoint... ")
            try:
                subprocess.check_call(
                    [_get_heroku_cli(), "certs:update", fullchain_path, key_path, "-a", heroku_app, "--confirm",
                     heroku_app, "--name", heroku_cert_name],
                    stdout=DEV_NULL)
            except subprocess.CalledProcessError:
                raise errors.PluginError("'heroku certs:update' command failed. See error above.")
        except subprocess.CalledProcessError:
            # Need to add SSL; it wasn't setup before
            logger.info("Configuring new Heroku SSL endpoint... ")
            try:
                subprocess.check_call([_get_heroku_cli(), "certs:add", fullchain_path, key_path, "-a", heroku_app],
                                      stdout=DEV_NULL)
            except subprocess.CalledProcessError:
                raise errors.PluginError("'heroku certs:add' command failed. See error above.")

    def get_all_names(self):
        return set()

    def supported_enhancements(self):  # pylint: disable=no-self-use
        return []

    def enhance(self, domain, enhancement, options=None):
        return

    def save(self, title=None, temporary=False):
        return

    def rollback_checkpoints(self, rollback=1):
        return

    def recovery_routine(self):
        return

    def view_config_changes(self):
        return

    def config_test(self):
        return

    def restart(self):
        return

    def get_all_certs_keys(self):
        return set()


def _validate_app(heroku_app):
    """Validates and returns the Heroku app name.

    :param str heroku_app: name of the Heroku app

    :returns: name of the Heroku app
    :rtype: str

    """
    try:
        subprocess.check_call([_get_heroku_cli(), "info", "-a", heroku_app], stdout=DEV_NULL)
    except subprocess.CalledProcessError:
        raise errors.PluginError(
            "No Heroku app named {0} was found. Make sure you have the Heroku "
            "CLI installed, and that running 'heroku info -a {0}' works.".format(heroku_app)
        )
    return heroku_app


def _get_heroku_cli():
    try:
        # Check if we need to add the custom domain to the Heroku app
        heroku_cli = subprocess.check_output(["which", "heroku"], stderr=DEV_NULL).strip()
    except subprocess.CalledProcessError:
        # Looking for heroku CLI at the usual places
        if os.path.isfile("/usr/local/heroku/bin/heroku"):
            heroku_cli = "/usr/local/heroku/bin/heroku"
        elif os.path.isfile("/usr/local/bin/heroku"):
            heroku_cli = "/usr/local/bin/heroku"
        else:
            raise errors.PluginError("Error: can't find Heroku CLI")
    return heroku_cli
