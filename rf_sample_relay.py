"""Count actual PCM bytes while transparently forwarding the existing audio pipe."""
import json
import os
from pathlib import Path
import sys

path=Path(sys.argv[1])
count=0
try:
    while True:
        block=os.read(0,65536)
        if not block:
            break
        count+=len(block)
        view=memoryview(block)
        while view:
            view=view[os.write(1,view):]
        # The evidence survives forced pipe cleanup; it is not a decoded result.
        temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'sample_bytes':count}))
        temporary.replace(path)
except BrokenPipeError:
    pass
