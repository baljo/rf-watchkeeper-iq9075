"""Static audit of the curated checkout; no RF, native inference or deletion."""
import ast,json,pathlib,re,subprocess,hashlib
from urllib.parse import unquote,urlsplit
ROOT=pathlib.Path(__file__).resolve().parents[3]
CURRENT=['README.md','docs/current-status.md','docs/architecture.md','docs/airband.md','docs/atis.md','docs/tower-anomaly.md','docs/operation.md','docs/rf-jobs.md','docs/dashboard.md','docs/data-retention.md','docs/ais.md','docs/meteor.md','docs/installation.md','docs/troubleshooting.md','docs/watchdog-and-recovery.md','docs/reliability.md','docs/testing-and-validation.md','docs/experiments.md','docs/project-history.md','docs/hardware.md','docs/433mhz.md','docs/location-privacy.md']
out={'current_documents':len(CURRENT),'local_links':0,'missing_current_links':[],'historical_missing_links':[],'python_syntax':[],'source_reference_misses':[]}
for n in CURRENT:
 p=ROOT/n;s=p.read_text(encoding='utf-8')
 if len(re.findall(r'^```',s,re.M))%2:raise ValueError('Unclosed code fence: '+n)
 for target in re.findall(r'(?<!!)\[[^\]]*\]\(([^)]+)\)',s):
  target=target.strip('<>')
  if urlsplit(target).scheme or target.startswith('#'):continue
  out['local_links']+=1
  dest=(p.parent/unquote(target.split('#')[0])).resolve()
  if not dest.exists():out['missing_current_links'].append({'file':n,'target':target})
 # Explicit simple application filenames in current guides must exist; external paths are documented separately.
 for name in set(re.findall(r'`([a-z][a-z0-9_]+\.py)`',s)):
  if not (ROOT/name).exists():out['source_reference_misses'].append({'file':n,'source':name})
for n in ['docs/project-log.md','docs/publication-manifest.md','docs/legacy/atis-poc.md','docs/legacy/audio-workflow.md','docs/legacy/autonomous-evk.md','docs/legacy/meteor-automation.md','docs/legacy/rf-health.md']:
 p=ROOT/n
 for target in re.findall(r'(?<!!)\[[^\]]*\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
  if urlsplit(target).scheme or target.startswith('#'):continue
  if not (p.parent/unquote(target.split('#')[0])).exists():out['historical_missing_links'].append({'file':n,'target':target,'disposition':'EVK-only chronological/stage evidence; unavailable in clone, explained in current-status and publication manifest'})
for p in list(ROOT.glob('*.py'))+list((ROOT/'backends').rglob('*.py'))+list((ROOT/'scripts').glob('*.py')):
 ast.parse(p.read_text(encoding='utf-8'),filename=p.name);out['python_syntax'].append(str(p.relative_to(ROOT)).replace('\\','/'))
settings=json.loads((ROOT/'config/examples/meteor-config.example.json').read_text());jobs=json.loads((ROOT/'jobs-v4.jsonc').read_text())
assert settings['sample_rate']==256000 and settings['frequency']==137900000 and not settings['cleanup_enabled'] and not settings['retention']['automatic_deletion_validated']
assert next(j for j in jobs['jobs'] if j['id']=='ais')['dwell_seconds']==45
assert next(j for j in jobs['jobs'] if j['id']=='vaasa-atis')['interval_seconds']==600
assert next(j for j in jobs['jobs'] if j['id']=='vaasa-tower')['max_listen_seconds']==75
out['config_checks']='METEOR recorded/current sample rate distinction and gates; V4 AIS/ATIS/Tower cadence/limits match audited live settings'
out['runtime_deploy_required']=False
assert not out['missing_current_links'],out['missing_current_links']
assert not out['source_reference_misses'],out['source_reference_misses']
(ROOT/'docs/evidence/repository-audit-20261010/validation.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:len(v) if isinstance(v,list) else v for k,v in out.items()},indent=2))
