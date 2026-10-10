"""Consecutive-capture ATIS agreement, not ASR confidence or numeric repair.

Input is newest first. Never skips a capture or searches for an older majority.
Every selected value requires two independent capture IDs; disagreement cannot
be outvoted. Pure/read-only so original transcripts and individual parses remain.
"""
from datetime import datetime
import json
from urllib.parse import quote
import atis_parser

VERSION='atis-consensus-v1'
MAX_GAP_SECONDS=900
MAX_SPAN_SECONDS=1800
IDENTITY=('information_identifier','observation_time_utc')
# Independent categories prevent direction+speed+gust from counting as three
# anchors, or temperature+dew point from counting as two.
STABLE_CATEGORIES=(('qnh_hpa',),('runway',),('wind_direction_deg','wind_speed_kt','gust_speed_kt'),
                   ('temperature_c','dew_point_c'),('visibility_m',),('cloud_layers',),('weather_phenomena',))

def stamp(row):
    try:
        value=datetime.fromisoformat(row['captured_at'].replace('Z','+00:00'))
        return value if value.tzinfo is not None else None
    except (KeyError,ValueError,TypeError,AttributeError):return None

def parsed(row):return row.get('structured_atis') or {}
def recognized(row,key):
    p=parsed(row)
    return p.get('fields',{}).get(key) if p.get('field_status',{}).get(key)=='recognized' else None

def canonical(value):
    # Only formatting equivalence; no digits, synonyms or units are repaired.
    if isinstance(value,str):value=' '.join(value.lower().split())
    if isinstance(value,list):value=sorted(value,key=lambda x:json.dumps(x,sort_keys=True))
    return json.dumps(value,sort_keys=True,ensure_ascii=False)

def candidates(row,key):
    p=parsed(row);values=[]
    value=recognized(row,key)
    if value is not None:values.append(value)
    if p.get('field_status',{}).get(key)=='conflicting':
        for value in p.get('conflicts',{}).get(key,[]):
            if not any(canonical(value)==canonical(v) for v in values):values.append(value)
    return values

def disagreements(group,row):
    changes={}
    for key in atis_parser.FIELDS:
        previous=[]
        for member in group:
            for value in candidates(member,key):
                if not any(canonical(value)==canonical(v) for v in previous):previous.append(value)
        older=candidates(row,key)
        if previous and older and any(canonical(a)!=canonical(b) for a in previous for b in older):
            changes[key]={'included_values':previous,'older_values':older}
    return changes

def eligible(row):
    if row.get('kind','atis')!='atis':return 'not_atis'
    if not row.get('recording') or stamp(row) is None:return 'invalid_capture_identity'
    if row.get('status') in ('pending','interrupted','no_activity','unavailable','waiting','failed'):
        return 'capture_not_usable'
    if (row.get('capture') or {}).get('status')=='interrupted':return 'capture_not_usable'
    if not any(recognized(row,k) is not None for k in atis_parser.FIELDS):return 'no_recognized_fields'
    if any(v=='conflicting' for v in parsed(row).get('field_status',{}).values()):return 'individual_conflict'
    return None

def match(a,b):
    identities=[key for key in IDENTITY if recognized(a,key) is not None and recognized(b,key) is not None
                and canonical(recognized(a,key))==canonical(recognized(b,key))]
    stable=[]
    for category in STABLE_CATEGORIES:
        equal=[key for key in category if recognized(a,key) is not None and recognized(b,key) is not None
               and canonical(recognized(a,key))==canonical(recognized(b,key))]
        if equal:stable.append(equal)
    allowed=len(identities)==2 or (len(identities)>=1 and len(stable)>=1) or len(stable)>=3
    return allowed,{'matching_identifiers':identities,'matching_stable_categories':stable,
                    'basis':'both_identifiers' if len(identities)==2 else 'identifier_and_stable_field' if identities and stable else 'three_independent_stable_categories'}

def reference(row):
    name=row['recording']
    return {'recording':name,'captured_at':row.get('captured_at'),
            'individual_url':'/api/atis?recording='+quote(name,safe=''),
            'audio_url':row.get('audio_url')}

def build(rows):
    """Consensus of only the consecutive group anchored to the newest capture."""
    group=[];joins=[];boundary=None
    if rows:
        first=rows[0];reason=eligible(first)
        if reason:
            boundary={'recording':first.get('recording'),'reason':reason,'changes':{},'latest_unusable':True}
        else:
            group=[first];seen={first['recording']}
            for row in rows[1:]:
                changes=disagreements(group,row)
                reason=None
                if row.get('recording') in seen:reason='duplicate_capture'
                elif stamp(row) is None:reason='invalid_capture_time'
                else:
                    gap=(stamp(group[-1])-stamp(row)).total_seconds()
                    span=(stamp(first)-stamp(row)).total_seconds()
                    if gap<=0:reason='nonconsecutive_capture_time'
                    elif gap>MAX_GAP_SECONDS:reason='capture_gap'
                    elif span>MAX_SPAN_SECONDS:reason='group_time_limit'
                # Time/provenance boundaries do not make a distant value a conflict.
                if reason:
                    boundary={'recording':row.get('recording'),'reason':reason,'changes':{}};break
                for key in ('source','job_id','frequency_hz'):
                    bv=(row.get('capture') or {}).get(key)
                    for member in group:
                        av=(member.get('capture') or {}).get(key)
                        if av is not None and bv is not None and av!=bv:reason='capture_context_change'
                if reason:
                    boundary={'recording':row.get('recording'),'reason':reason,'changes':{}};break
                identity_changes={k:v for k,v in changes.items() if k in IDENTITY}
                if identity_changes:reason='message_identity_change'
                elif changes:reason='material_field_disagreement'
                else:reason=eligible(row)
                if reason:
                    boundary={'recording':row.get('recording'),'reason':reason,'changes':changes};break
                allowed,proof=match(group[-1],row)
                if not allowed:
                    boundary={'recording':row.get('recording'),'reason':'insufficient_message_match','changes':{}};break
                joins.append(dict(proof,newer_recording=group[-1]['recording'],older_recording=row['recording']))
                group.append(row);seen.add(row['recording'])
    fields={};states={};support={};evidence={};conflicts={}
    # Retain newest individual conflict evidence even if it prevents grouping.
    voters=group or rows[:1]
    for key in atis_parser.FIELDS:
        variants=[];agreeing=[];quotes=[];unknown=[]
        for row in voters:
            vals=candidates(row,key)
            for value in vals:
                if not any(canonical(value)==canonical(v) for v in variants):variants.append(value)
            if recognized(row,key) is not None and row.get('recording'):agreeing.append(row['recording'])
            else:unknown.append(row.get('recording'))
            for item in parsed(row).get('evidence',{}).get(key,[]):
                quotes.append(dict(item,recording=row.get('recording'),captured_at=row.get('captured_at')))
        ambiguous_boundary=boundary and boundary['reason']=='material_field_disagreement' and key in boundary['changes']
        if ambiguous_boundary:
            for value in boundary['changes'][key]['older_values']:
                if not any(canonical(value)==canonical(v) for v in variants):variants.append(value)
            excluded=next(r for r in rows if r.get('recording')==boundary['recording'])
            for item in parsed(excluded).get('evidence',{}).get(key,[]):
                quotes.append(dict(item,recording=excluded.get('recording'),captured_at=excluded.get('captured_at'),excluded_at_boundary=True))
        count=len(set(agreeing)) if group else 0
        conflict=len(variants)>1 or any(parsed(row).get('field_status',{}).get(key)=='conflicting' for row in voters)
        fields[key]=variants[0] if len(variants)==1 and count>=2 and not conflict else None
        states[key]='conflicting' if conflict else 'agreed' if fields[key] is not None else 'single_observation' if count==1 else 'unknown'
        support[key]={'agreeing_capture_count':count,'recordings':list(dict.fromkeys(agreeing)) if group else [],'unknown_recordings':unknown}
        evidence[key]=quotes
        if conflict:conflicts[key]=variants
    agreed=sum(v=='agreed' for v in states.values())
    return {'consensus_version':VERSION,'parser_version':atis_parser.VERSION,
        'latest_recording':rows[0].get('recording') if rows else None,
        'status':'complete' if agreed==len(atis_parser.FIELDS) else 'partial' if agreed else 'insufficient_evidence' if rows else 'unavailable',
        'fields':fields,'field_status':states,'support':support,'evidence':evidence,'conflicts':conflicts,
        'group':{'capture_count':len(group),'captures':[reference(row) for row in group],'joins':joins,
                 'start_at':group[-1].get('captured_at') if group else None,'end_at':group[0].get('captured_at') if group else None},
        'boundary':boundary,'policy':{'max_gap_seconds':MAX_GAP_SECONDS,'max_span_seconds':MAX_SPAN_SECONDS,
            'minimum_field_support':2,'no_majority_vote':True,'no_capture_skipping':True},
        'quality':{'agreed_fields':agreed,'supported_fields':len(atis_parser.FIELDS),'basis':'Distinct capture agreement counts; not ASR confidence or audio verification.'},
        'human_review_required':True}
