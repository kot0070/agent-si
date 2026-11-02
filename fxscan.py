import json, re

def flatten(o, p=''):
    out = []
    for k, v in o.items():
        if isinstance(v, dict):
            out += flatten(v, p + k + '.')
        else:
            out.append(p + k)
    return sorted(out)

en = json.load(open('D:/AI_PROJECTS/AGENT_SI_BUILD/WT/R02/frontend/src/locale/en.json', encoding='utf-8'))
dts = open('D:/AI_PROJECTS/AGENT_SI_BUILD/WT/R02/frontend/src/settings/k07b-iface.d.ts', encoding='utf-8').read()
block = re.search(r'export type LocaleKey =([\s\S]*?);', dts).group(1)
union = sorted(set(re.findall(r"'([^']+)'", block)))
ek = flatten(en)
print('json leaves', len(ek), 'union', len(union))
print('MISSING FROM UNION:')
for k in ek:
    if k not in union:
        print(' ', k)
print('EXTRA IN UNION:')
for k in union:
    if k not in ek:
        print(' ', k)
