import json
for path in ['src/locale/en.json', 'src/locale/uk.json']:
    d = json.load(open(path, encoding='utf-8'))
    d['shell']['skipToComposer'] = 'Skip to composer' if path.endswith('en.json') else '\u041f\u0435\u0440\u0435\u0439\u0442\u0438 \u0434\u043e \u0432\u0432\u0435\u0434\u0435\u043d\u043d\u044f'
    open(path, 'w', encoding='utf-8').write(json.dumps(d, ensure_ascii=False, separators=(',', ':')))
    print(path, repr(d['shell']['skipToComposer']))
