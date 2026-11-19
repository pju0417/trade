"""Put the frozen engine, sim_lib and the webapp module on sys.path (repo layout)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in (os.path.join(ROOT, 'claude_review'), os.path.join(ROOT, 'webapp', 'py')):
    if p not in sys.path:
        sys.path.insert(0, p)
