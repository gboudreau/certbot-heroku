from setuptools import setup
from setuptools import find_packages

version = '0.0.1'

setup(
    name='certbot-heroku',
    version=version,
    description="REST/Heroku plugin for certbot",
    url='https://github.com/jeppeliisberg/certbot-heroku',
    author="Jeppe Liisberg",
    author_email='jeppe@liisberg.net',
    license='Apache License 2.0',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Plugins',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Security',
        'Topic :: System :: Installation/Setup',
        'Topic :: System :: Networking',
        'Topic :: System :: Systems Administration',
        'Topic :: Utilities',
    ],
    packages=find_packages(),
    install_requires=[
        'acme',
        'certbot',
        'zope.interface',
    ],
    entry_points={
        'certbot.plugins': [
            'heroku = certbot_heroku.configurator:HerokuConfigurator',
        ],
    },
)
