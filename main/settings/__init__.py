import sys
from .base import *

RUNNING_PYTEST = 'pytest' in sys.modules or any('pytest' in arg for arg in sys.argv)

if os.getenv('CI') == 'true' or os.getenv('GITHUB_ACTIONS') == 'true':
    from .ci import *
elif RUNNING_PYTEST:
    from .test import *
else:
    # you need to set "myproject = 'prod'" as an environment variable
    # in your OS (on which your website is hosted)
    if 'env' in os.environ:
        if os.environ['env'] == 'prod':
            from .prod import *
        elif os.environ['env'] == 'staging':
            from .staging import *
    else:
        from .dev import *
