import re
css = open('src/ui/tokens.css', encoding='utf-8').read()
def tokenValue(block, name):
    m = re.search(block + r'\s*\{([\s\S]*?)\}', css, re.M)
    if not m:
        return 'BLOCK-NOT-FOUND'
    line = [l for l in m.group(1).split(';') if name in l]
    return line
print(tokenValue(r'\[data-theme="dark"\]', '--fx-placeholder'))
print(tokenValue(r'\[data-theme="dark"\]', '--fx-input-bg'))
print(tokenValue(r'\[data-theme="light"\]', '--fx-placeholder'))
print(tokenValue(r'\[data-theme="light"\]', '--fx-input-bg'))
