import os, getpass

if 'HARVEST_DATABASE' not in os.environ:
    print('Warning: HARVEST_DATABASE is not set.')
    print('Eg: export HARVEST_DATABASE="sqlite:////home/%s/.harvest.db"' % getpass.getuser())
    SQLALCHEMY_DATABASE_URI = ''
else:
    SQLALCHEMY_DATABASE_URI = os.environ['HARVEST_DATABASE']

MASTER_KEY        = None
MASTER_KEY_NAME   = "Primary"
PERMIT_NEW        = False
GZIP_HERE         = True
COMPRESS_ARTICLES = True
ENABLE_CORS       = False
if "NO_DUPLICATE_TITLES" in os.environ:
    NO_DUPLICATE_TITLES = os.environ['NO_DUPLICATE_TITLES']
else:
    NO_DUPLICATE_TITLES = True
