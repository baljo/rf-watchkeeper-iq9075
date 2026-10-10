"""ASR-independent, conservative Tower screening from saved acoustic evidence."""
import json
from pathlib import Path
from datetime import datetime, timezone

def read(path):
    try: return json.loads(path.read_text())
    except (OSError, ValueError): return {}

def classify(folder):
    folder=Path(folder)
    capture=read(folder/'capture.json')
    segmentation=read(folder/'segmentation.json')
    hold=capture.get('activity_hold') or {}
    # Energy activity is plausible speech, never a claim of intelligibility.
    active=bool(hold.get('triggered') or segmentation.get('regions') or segmentation.get('status')=='activity_detected')
    quiet=segmentation.get('status') in ('no_activity','silence','no_speech') and not active
    status='voice_candidate' if active else ('probably_non_voice' if quiet else 'uncertain')
    message={'voice_candidate':'voice candidate — manual review required','probably_non_voice':'probably non-voice/noise — listening review available','uncertain':'uncertain — manual review required'}[status]
    return dict(status=status,message=message,manual_review_required=not quiet,classification=status,
                method='saved-acoustic-evidence-v1',evidence={'activity_hold':hold,'segmentation':segmentation},
                asr_status='disabled',asr_required=False)

def process(folder):
    import os,tempfile
    folder=Path(folder)
    result=classify(folder)
    result.update(processed_at=datetime.now(timezone.utc).isoformat(),transcript_status='disabled',interpretation_status='not_run')
    # Keep historical processing, transcripts, audio and labels untouched.
    fd,tmp=tempfile.mkstemp(dir=folder,prefix='.tower-classification-')
    with os.fdopen(fd,'w') as f: json.dump(result,f,indent=2)
    Path(tmp).replace(folder/'tower-classification.json')
    return result
