import sys
from .base import *

RUNNING_PYTEST = 'pytest' in sys.modules or any('pytest' in arg for arg in sys.argv)

if os.getenv('CI') == 'true' or os.getenv('GITHUB_ACTIONS') == 'true':
    from .ci import *
    print("### SETTINGS ci")
elif RUNNING_PYTEST:
    from .test import *
    print("### SETTINGS test")
else:
    if 'env' in os.environ:
        if os.environ['env'] == 'prod':
            print("### SETTINGS prod")
            from .prod import *
        elif os.environ['env'] == 'staging':
            print("### SETTINGS staging")
            from .staging import *
    else:
        from .dev import *
        print("### SETTINGS dev")
