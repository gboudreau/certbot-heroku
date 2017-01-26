"""Heroku plugin."""
import argparse
import collections
import logging
import os
import subprocess
import time

import zope.component
import zope.interface

from acme import challenges

from certbot import errors
from certbot import interfaces
from certbot.display import util as display_util
from certbot.plugins import common


logger = logging.getLogger(__name__)

DEV_NULL = open(os.devnull, 'w')


@zope.interface.implementer(interfaces.IAuthenticator, interfaces.IInstaller)
@zope.interface.provider(interfaces.IPluginFactory)
class HerokuConfigurator(common.Plugin):
    """Heroku configurator."""

    description = "Heroku SSL"

    MORE_INFO = """\
Plugin that performs hostname validation using Heroku by
setting a config var, then installs the generated certificate with
Heroku SSL. It expects that your Heroku app is already
configured to serve the proper response when it receives the ACME
challenge request, and that the Heroku CLI is already installed
and functional. See https://github.com/gboudreau/certbot-heroku for
detailed set-up instructions."""

    def more_info(self):  # pylint: disable=missing-docstring,no-self-use
        return self.MORE_INFO

    @classmethod
    def add_parser_arguments(cls, add):
        add("app", "-H", default=[], action=_HerokuAppAction,
            help="The name of your Heroku app. This can be specified multiple "
                 "times to handle different domains; each domain will use "
                 "the Heroku app that preceded it.  For instance: `-H "
                 "MyApp -d example.com -d www.example.com -H "
                 "MyAppDev -d dev.example.com` (default: Ask)")
        add("configvar", default="LETS_ENCRYPT_CHALLENGE", action=_HerokuConfigVarAction,
            help="The name of the Heroku config var that needs to be set "
                 "for your Heroku app to correctly answer the ACME challenge. "
                 "(default: LETS_ENCRYPT_CHALLENGE)")

    def get_chall_pref(self, domain):  # pragma: no cover
        # pylint: disable=missing-docstring,no-self-use,unused-argument
        return [challenges.HTTP01]

    def __init__(self, *args, **kwargs):
        super(HerokuConfigurator, self).__init__(*args, **kwargs)
        if not hasattr(self.config, self.dest('map')):
            setattr(self.config, self.dest('map'), {})
        self.performed = collections.defaultdict(set)

    def prepare(self):  # pylint: disable=missing-docstring
        pass

    def perform(self, achalls):  # pylint: disable=missing-docstring
        domains = []
        for achall in achalls:
            domains.append(achall.domain)
        self._set_heroku_apps(domains)

        self._check_heroku_apps_map()

        return [self._perform_single(achall) for achall in achalls]

    def _set_heroku_apps(self, domains):
        if self.conf("app"):
            heroku_app = self.conf("app")[-1]
            for domain in domains:
                if domain not in self.conf("map"):
                    self.conf("map").setdefault(domain, heroku_app)
        else:
            for domain in domains:
                if domain not in self.conf("map"):
                    new_heroku_app = self._prompt_for_heroku_app(domain)
                    self.conf("map")[domain] = new_heroku_app

    def _prompt_for_heroku_app(self, domain):
        heroku_app = None

        while heroku_app is None:
            heroku_app = self._prompt_for_new_app(domain)

        return heroku_app

    def _prompt_for_new_app(self, domain):
        display = zope.component.getUtility(interfaces.IDisplay)

        while True:
            code, heroku_app = display.input(
                "Input the Heroku app name for {0}:".format(domain),
                force_interactive=True)
            if code == display_util.HELP:
                # Displaying help is not currently implemented
                return None
            elif code == display_util.CANCEL:
                return None
            else:  # code == display_util.OK
                try:
                    return _validate_app(heroku_app)
                except errors.PluginError as error:
                    display.notification(str(error), pause=False)

    def _check_heroku_apps_map(self):
        if not self.conf("map"):
            raise errors.PluginError(
                "Missing parts of Heroku configuration; please set "
                "-H and --domains. Run with --help heroku for examples.")

    def _perform_single(self, achall):
        response, validation = achall.response_and_validation()

        heroku_app = self.conf("map")[achall.domain]
        config_value = "{0}={1}".format(self.conf("configvar"), validation.encode())

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

        try:
            # Check if we need to disable preboot
            ps = subprocess.Popen([_get_heroku_cli(), "features", "-a", heroku_app], stdout=subprocess.PIPE)
            subprocess.check_call(['grep', "+.*preboot"], stdin=ps.stdout, stdout=DEV_NULL)
            ps.wait()

            preboot_was_enabled = True
            logger.warning("  Disabling preboot feature")
            subprocess.call([_get_heroku_cli(), "features:disable", "preboot", "-a", heroku_app], stdout=DEV_NULL)
        except subprocess.CalledProcessError:
            # preboot is not enabled; all is good
            preboot_was_enabled = False

        logger.info("  Saving ACME challenge response in config var")
        try:
            subprocess.check_call([_get_heroku_cli(), "config:set", config_value, "-a", heroku_app], stdout=DEV_NULL)
        except subprocess.CalledProcessError:
            raise errors.PluginError(
                "Failed to use 'heroku config:set' to set the config var {0} "
                "for the Heroku app named {1}. Make sure the Heroku CLI is installed, "
                "and that running 'heroku info -a {1}' works.".format(config_value, heroku_app)
            )

        logger.info("  Waiting for web dynos to restart...")
        while True:
            time.sleep(5)  # Need to wait until Heroku finished restarting the web dynos
            try:
                ps = subprocess.Popen([_get_heroku_cli(), "ps", "web", "-a", heroku_app], stdout=subprocess.PIPE)
                subprocess.check_call(['grep', "starting"], stdin=ps.stdout, stdout=DEV_NULL)
                ps.wait()
                # Dynos are still restarting; continue waiting...
            except subprocess.CalledProcessError:
                # Dynos finished restarting; let the ACME server do its validation
                break

        if preboot_was_enabled:
            logger.warning("  Re-enabling preboot feature")
            subprocess.call([_get_heroku_cli(), "features:enable", "preboot", "-a", heroku_app], stdout=DEV_NULL)

        self.performed[heroku_app].add(achall)

        return response

    def cleanup(self, achalls):  # pylint: disable=missing-docstring
        for achall in achalls:
            heroku_app = self.conf("map")[achall.domain]
            logger.info("Clearing ACME challenge response config var from '%s'", heroku_app)
            subprocess.check_call([_get_heroku_cli(), "config:unset", self.conf("configvar"), "-a", heroku_app],
                                  stdout=DEV_NULL)

    #####
    # Installer
    #####

    # Entry point in main.py for installing cert
    def deploy_cert(self, domain, cert_path, key_path, chain_path=None, fullchain_path=None):
        # pylint: disable=unused-argument

        if domain not in self.conf("map"):
            self._set_heroku_apps([domain])

        heroku_app = self.conf("map")[domain]
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
                     heroku_app],
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
        all_names = set()

        for domain, app in self.conf("map").items():
            if domain not in all_names:
                all_names.add(domain)

        return all_names

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


class _HerokuConfigVarAction(argparse.Action):
    """Action class for parsing heroku_config_var."""

    def __call__(self, parser, namespace, heroku_config_var, option_string=None):
        if heroku_config_var:
            namespace.heroku_config_var = heroku_config_var


class _HerokuAppAction(argparse.Action):
    """Action class for parsing heroku_app."""

    def __init__(self, *args, **kwargs):
        super(_HerokuAppAction, self).__init__(*args, **kwargs)
        self._domain_before_app = False

    def __call__(self, parser, namespace, heroku_app, option_string=None):
        if self._domain_before_app:
            raise errors.PluginError(
                "If you specify multiple Heroku apps, "
                "one of them must precede all domain flags.")

        if getattr(namespace, 'certbot_heroku:heroku_app'):
            # Apply previous app to all matched
            # domains before setting the new app
            prev_app = getattr(namespace, 'certbot_heroku:heroku_app')[-1]
            for domain in namespace.domains:
                if 'certbot_heroku:heroku_map' not in namespace:
                    setattr(namespace, 'certbot_heroku:heroku_map', {})
                getattr(namespace, 'certbot_heroku:heroku_map').setdefault(domain, prev_app)
        elif namespace.domains:
            self._domain_before_app = True

        getattr(namespace, 'certbot_heroku:heroku_app').append(_validate_app(heroku_app))


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
