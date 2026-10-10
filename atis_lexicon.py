"""Small, explicit ATIS vocabulary. No fuzzy matching or numeric repair.

Each replacement maps back to the complete original token span. Corrections
are auditable and never overwrite the retained transcript.
"""
import re

VERSION = 'atis-lexicon-v1'
NUMBER = r'(?:\d+|zero|one|wun|two|to|too|three|tree|four|fower|for|five|fife|six|seven|eight|ait|ate|nine|niner|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand)'

def correct(text):
    """Return corrected text, original-character map, and applied rule history."""
    origins=[(i,i+1) for i in range(len(text))]
    history=[]
    original=text
    def replace(pattern, replacement, rule):
        nonlocal text,origins
        for m in reversed(list(re.finditer(pattern,text,re.I))):
            value=replacement(m) if callable(replacement) else replacement
            if m.group()==value:continue
            start,end=origins[m.start()][0],origins[m.end()-1][1]
            history.append({'rule':rule,'original':original[start:end],
                            'replacement':value,'span':[start,end]})
            text=text[:m.start()]+value+text[m.end():]
            origins=origins[:m.start()]+[(start,end)]*len(value)+origins[m.end():]
    # Explicit spellings/abbreviations; ambiguous ordinary words require context.
    replace(r'\bdew[ -]+point\b','dew point','dew-point')
    replace(r'\brun[ -]+way\b','runway','runway')
    replace(r'\bvisibilty(?=\s+'+NUMBER+r'\b)','visibility','visibility-spelling')
    replace(r'\btemprature(?=\s+(?:(?:minus|negative|plus)\s+)?'+NUMBER+r'\b)','temperature','temperature-spelling')
    replace(r'(?<=wind )VRB\b','variable','variable-wind')
    replace(r'\bdeparting(?=\s+runway\b)','departure','departing-runway')
    replace(r'\b(?:i\s+l\s+s|r\s+n\s+p|r\s+n\s+a\s+v)(?=\s+approach\b)',
            lambda m:re.sub(r'\s+','',m.group()).upper(),'approach-abbreviation')
    replace(r'(?<=information )alfa\b','alpha','information-alfa')
    replace(r'(?<=information )juliett\b','juliet','information-juliett')
    replace(r'(?<=information )x[ -]ray\b','xray','information-xray')
    replace(r'\bCNAH(?=\s*[, :\-]?\s*'+NUMBER+r'\b)','QNH','qnh-cnah')
    replace(r'\b(?:q\s+n\s+h|q\s+and\s+h|cue\s+en\s+(?:aitch|h))\b','QNH','qnh-spelling')
    # An ASR homophone for knots is accepted only after a complete wind clause.
    replace(r'\b(?:knock|nots)\b',lambda m:'knots' if re.search(
        r'\bwind\s+(?:(?:touchdown|cut\s+down)\s+zone\s+)?'
        +NUMBER+r'(?:[\s,\-]+'+NUMBER+r'){0,5}\s*[,;]?\s+(?:degrees?|regrees)\s*[,;]?\s*'
        +NUMBER+r'(?:[\s,\-]+'+NUMBER+r'){0,5}\s*[,;]?\s*$',
        text[max(0,m.start()-180):m.start()],re.I) else m.group(),'wind-knots')
    replace(r'\bregrees\b',lambda m:'degrees' if re.search(r'\bwind\b[^.;!?]{0,120}$',text[:m.start()],re.I) else m.group(),'wind-degrees')
    replace(r'\b(?:SCT|BKN|OVC)(?=\s+'+NUMBER+r'\b)',
            lambda m:{'SCT':'scattered','BKN':'broken','OVC':'overcast'}[m.group().upper()],'cloud-abbreviation')
    replace(r'\b(?:km|m)(?=\b)',lambda m:({'km':'kilometres','m':'metres'}[m.group().lower()]
        if re.search(r'\bvisibility\s+(?:is\s+)?'+NUMBER+r'(?:[\s,\-]+'+NUMBER+r'){0,5}\s*$',text[:m.start()],re.I) else m.group()),'visibility-unit')
    replace(r'\bft\b',lambda m:'feet' if re.search(r'\b(?:few|scattered|broken|overcast)\s+(?:clouds?\s+)?(?:at\s+)?'+NUMBER+r'(?:[\s,\-]+'+NUMBER+r'){0,5}\s*$',text[:m.start()],re.I) else m.group(),'cloud-unit')
    # Weather abbreviations require an explicit weather label, preserving negation.
    codes={'RA':'rain','DZ':'drizzle','SN':'snow','SHRA':'rain showers','SHSN':'snow showers',
           'FZRA':'freezing rain','FZDZ':'freezing drizzle','TS':'thunderstorm','FG':'fog','BR':'mist','HZ':'haze'}
    replace(r'(?<=weather )(?:(?:RA|DZ|SN|SHRA|SHSN|FZRA|FZDZ|TS|FG|BR|HZ))\b',
            lambda m:codes[m.group().upper()] if not re.search(
                r'\b(?:no|not|without|expect|expected|forecast)\b[^.;!?]{0,40}$',text[:m.start()],re.I) else m.group(),
            'weather-abbreviation')
    return {'text':text,'origins':origins,'corrections':sorted(history,key=lambda x:x['span']),
            'version':VERSION}
