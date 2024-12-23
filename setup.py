from setuptools import setup

APP = ['coin.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': True,
    'packages': ['flask_cors','flask','requests','logging'],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
