"""Conservative ATIS parsing of ASR evidence; never modifies input transcripts.

Recognition confidence means a supported grammar and range, not ASR probability.
Candidates are parsed per segment; disagreement leaves a field unknown.
"""
import re
import atis_lexicon

VERSION = 'atis-context-v2'
DIGITS = dict(zip('zero wun one to too two tree three fower for four fife five six seven ait ate eight niner nine'.split(),
                  '0 1 1 2 2 2 3 3 4 4 4 5 5 6 7 8 8 8 9 9'.split()))
CARDINAL = {'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,
            'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19,'twenty':20,
            'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90}
WORDS = '|'.join(sorted(list(DIGITS)+list(CARDINAL), key=len, reverse=True))
ATOM = r'(?:\d+(?:\.\d+)?|hundred|thousand|'+WORDS+r')\b'
NUM = ATOM+r'(?:[\s,\-]+'+ATOM+r'){0,5}'
NATO = 'ALPHA BRAVO CHARLIE DELTA ECHO FOXTROT GOLF HOTEL INDIA JULIET KILO LIMA MIKE NOVEMBER OSCAR PAPA QUEBEC ROMEO SIERRA TANGO UNIFORM VICTOR WHISKEY XRAY YANKEE ZULU'.split()
FIELDS = ['information_identifier','observation_time_utc','wind_direction_deg','wind_speed_kt',
          'gust_speed_kt','visibility_m','weather_phenomena','cloud_layers','temperature_c',
          'dew_point_c','qnh_hpa','runway','approach_wording','landing_wording','departure_wording']

def number(text, width=None):
    """Parse only an already context-delimited number, rejecting mixed/partial forms."""
    parts=re.findall(r'\d+(?:\.\d+)?|[a-z]+',text.lower())
    if not parts:return None
    if not width and ('hundred' in parts or 'thousand' in parts):
        # Explicit magnitude words are accepted only inside field grammars.
        total=0;group=0;pending=[]
        for token in parts:
            if token not in ('hundred','thousand'):
                pending.append(token);continue
            value=number(' '.join(pending)) if pending else None
            if value is None:return None
            pending=[]
            if token=='hundred':group+=value*100
            else:total+=(group+value)*1000;group=0
        tail=number(' '.join(pending)) if pending else 0
        return total+group+tail if tail is not None else None
    if len(parts)==1 and parts[0].isdigit():
        if width and len(parts[0])!=width:return None
        return int(parts[0])
    if all(p in DIGITS for p in parts):
        if width and len(parts)!=width:return None
        return int(''.join(DIGITS[p] for p in parts))
    if not width and len(parts)==1 and parts[0] in CARDINAL:return CARDINAL[parts[0]]
    if not width and len(parts)==2 and CARDINAL.get(parts[0],0)>=20 and parts[1] in DIGITS:
        return CARDINAL[parts[0]]+int(DIGITS[parts[1]])
    return None

def parse(transcript):
    """Accept text or retained transcript dict; return fields plus source evidence."""
    segments=[{'text':transcript}] if isinstance(transcript,str) else (transcript or {}).get('segments',[])
    candidates={k:[] for k in FIELDS}
    corrections=[]
    for index,segment in enumerate(segments):
        if segment.get('status') in ('failed','no_speech'):continue
        # Prefer exact Qualcomm text; strip only timestamp markers for parsing.
        text=(segment.get('raw') or {}).get('text',segment.get('raw_text',segment.get('text','')))
        if not isinstance(text,str):continue
        original_text=text
        text=re.sub(r'\[\d+ms\s*-\s*\d+ms\]',lambda m:' '*len(m.group()),text)
        lexical=atis_lexicon.correct(text)
        text=lexical['text'];origins=lexical['origins']
        for correction in lexical['corrections']:
            correction=dict(correction,segment_index=index,start_seconds=segment.get('start_seconds'))
            corrections.append(correction)
        offset=segment.get('start_seconds')
        def matches(pattern):return re.finditer(pattern,text,re.I)
        def put(field,value,m):
            if value is None:return
            start,end=origins[m.start()][0],origins[m.end()-1][1]
            candidates[field].append({'value':value,'quote':original_text[start:end],
                'segment_index':index,'start_seconds':offset,'span':[start,end],
                'corrected_quote':m.group(),
                'lexical_corrections':[c for c in lexical['corrections'] if c['span'][0]<end and c['span'][1]>start]})
        for m in matches(r'\binformation\s+('+'|'.join(NATO)+r'|juliett|x-ray|alfa|[A-Z])\b'):
            v=m[1].upper()
            if len(v)==1:v=NATO[ord(v)-ord('A')]
            put('information_identifier',{'ALFA':'ALPHA','JULIETT':'JULIET','X-RAY':'XRAY'}.get(v,v),m)
        for m in matches(r'\b(?:at\s+)?time\s+('+NUM+r')(?:\s*(?:UTC|Zulu)\b)?'):
            n=number(m[1],4)
            if n is not None and n//100<24 and n%100<60:put('observation_time_utc','%02d:%02dZ'%(n//100,n%100),m)
        for m in matches(r'\b(?:q\s*n\s*h|q\s+and\s+h|cue\s+en\s+(?:aitch|h))\s*[:\-]?\s*('+NUM+r')'):
            n=number(m[1]);put('qnh_hpa',n if n is not None and 850<=n<=1100 else None,m)
        for m in matches(r'\brunway\s+('+NUM+r')(?:\s*(left|right|centre|center|[LRC])\b)?'):
            n=number(m[1]);suffix=(m[2] or '').upper()
            if n is not None and 1<=n<=36:
                put('runway','%02d'%n+({'LEFT':'L','RIGHT':'R','CENTRE':'C','CENTER':'C'}.get(suffix,suffix)),m)
        wind_prefix=r'\bwind\s+(?:(?:touchdown|cut\s+down)\s+zone\s+)?'
        degree=r'(?:degrees?|degre[e]?s|regrees)'
        for m in matches(wind_prefix+'('+NUM+r')\s*[,;]?\s+'+degree+r'\b'):
            n=number(m[1],3);put('wind_direction_deg',n if n is not None and 0<=n<=360 else None,m)
        for m in matches(wind_prefix+'('+NUM+r')\s*[,;]?\s+'+degree+r'\s*[,;]?\s*(?:at\s+)?('+NUM+r')(?:\s+(?:gust(?:ing|s)?\s*)('+NUM+r'))?\s*[,;]?\s+(?:knots?|nots|kt|kts)\b(?:\s+gust(?:ing|s)?\s+('+NUM+r')\s+(?:knots?|nots|kt|kts)\b)?'):
            direction=number(m[1],3);speed=number(m[2]);gust=number(m[3]) if m[3] else None
            if direction is not None and 0<=direction<=360 and speed is not None and 0<=speed<=150 and (not m[3] or gust is not None and speed<=gust<=200):
                put('wind_direction_deg',direction,m);put('wind_speed_kt',speed,m);put('gust_speed_kt',gust,m)
                if m[4]:
                    later=number(m[4]);put('gust_speed_kt',later if later is not None and speed<=later<=200 else None,m)
        for m in matches(r'\bwind\s+calm\b'):put('wind_speed_kt',0,m)
        for m in matches(r'\bwind\s+variable\s+('+NUM+r')\s+(?:knots|nots|kt|kts)\b'):
            n=number(m[1]);put('wind_speed_kt',n if n is not None and 0<=n<=150 else None,m)
        for m in matches(r'\b(temperature|dew\s*point)\s*(?:is\s+)?(minus|negative|plus)?\s*('+NUM+r')'):
            n=number(m[3]);n=-n if n is not None and m[2] and m[2].lower() in ('minus','negative') else n
            put('temperature_c' if m[1].lower()=='temperature' else 'dew_point_c',n if n is not None and -80<=n<=60 else None,m)
        for m in matches(r'\bvisibility\s*(?:is\s+)?('+NUM+r')\s*(kilomet(?:er|re)s?|met(?:er|re)s?)\b'):
            n=number(m[1]);n=n*1000 if n is not None and m[2].lower().startswith('kilo') else n
            put('visibility_m',n if n is not None and 0<=n<=100000 else None,m)
        for m in matches(r'\bCAVOK\b'):put('visibility_m',10000,m) # operational lower bound, see metadata
        # Only explicit phenomena; do not turn generic words into weather codes.
        weather=[m for m in matches(r'\b(?:light |moderate |heavy )?(?:freezing rain|freezing drizzle|rain showers|snow showers|rain|drizzle|snow|thunderstorms?|fog|mist|haze)\b')
                 if not re.search(r'\b(?:no|not|without|expect|expected|forecast)\s*$',text[max(0,m.start()-30):m.start()],re.I)]
        if weather:
            for m in weather:put('weather_phenomena',sorted({x.group().lower() for x in weather}),m)
        layers=[];layer_matches=[]
        for m in matches(r'\b(few|scattered|broken|overcast)\s+(?:clouds?\s+)?(?:at\s+)?('+NUM+r')\s*(hundred\s*(?:feet|foot)?|thousand\s*(?:feet|foot)?|feet|foot)?\b'):
            n=number(m[2]);unit=(m[3] or '').lower()
            if n is None:continue
            if unit.startswith('hundred'):n*=100
            elif unit.startswith('thousand'):n*=1000
            elif not unit:
                # Standard three-digit cloud groups encode hundreds of feet.
                if number(m[2],3) is None:continue
                n*=100
            if 0<=n<=60000:
                layers.append({'coverage':m[1].upper(),'height_ft':n});layer_matches.append(m)
        if layers:
            unique=sorted({(x['coverage'],x['height_ft']) for x in layers})
            for m in layer_matches:put('cloud_layers',[{'coverage':a,'height_ft':b} for a,b in unique],m)
        for field,pattern in [('approach_wording',r'\b(?:ILS|RNP|RNAV|visual)\s+approach\b'),
                              ('landing_wording',r'\b(?:landing\s+runway\s+'+NUM+r'|runway\s+'+NUM+r'\s+for\s+landing)\b'),
                              ('departure_wording',r'\b(?:departure\s+runway\s+'+NUM+r'|runway\s+'+NUM+r'\s+for\s+departure)\b')]:
            for m in matches(pattern):put(field,m.group(),m)
    fields={};states={};conflicts={}
    for field,items in candidates.items():
        values=[]
        for item in items:
            if item['value'] not in values:values.append(item['value'])
        fields[field]=values[0] if len(values)==1 else None
        states[field]='recognized' if len(values)==1 else ('conflicting' if values else 'unknown')
        if len(values)>1:conflicts[field]=values
    return {'parser_version':VERSION,'fields':fields,'field_status':states,'evidence':candidates,
            'lexical_version':atis_lexicon.VERSION,'lexical_corrections':corrections,
            'conflicts':conflicts,'human_review_required':True,
            'confidence_basis':'context_and_range_checks; no ASR probabilities',
            'visibility_note':'CAVOK implies visibility at least 10000 m; parsed values remain ASR-derived'}
