#!/usr/bin/env python3
# _*_ coding: utf-8 _*_
from setuptools import setup, find_packages

setup(
    name='Harvest',
    version="3.0.0",
    description='A microservice for indexing the plain text of articles and essays',
    author='Luke Brooks',
    author_email='luke@psybernetics.org.uk',
    url='http://psybernetics.org.uk/harvest',
    packages=['harvest', 'harvest.resources', 'harvest.controllers'],
    include_package_data=True,
    install_requires=[
        "setproctitle",
        "goose3",
        "lxml",
        "tornado",
        "uvloop",
        "Flask",
        "Flask-RESTful",
        "Flask-SQLAlchemy",
        "cssselect",
        "beautifulsoup4",
        "feedparser",
        "python-snappy",
        "requests",
        "pygments",
    ],
    entry_points={
        "console_scripts": [
            "harvest = harvest.run:cli",
        ],
    },
    keywords=["text extraction", "document archival", "document retrieval"]
)
