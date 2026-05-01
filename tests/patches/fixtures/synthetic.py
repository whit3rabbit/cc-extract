"""Hand-crafted JS snippets per patch.

Each snippet is the smallest possible chunk that exercises the patch's
anchor regex. They are NOT minified Claude Code; they exist for fast
iteration during a port and for catching obvious anchor breakages
without downloading a real binary."""

SYNTHETIC = {
    "hide-startup-banner": (
        ',R.createElement(B,{isBeforeFirstMessage:!1}),'
        'function banner(){if(x)return"Apple_Terminal";return"Welcome to Claude Code"}'
    ),
    "hide-startup-clawd": (
        'function inner(){return"\\u259B\\u2588\\u2588\\u2588\\u259C"}'
        'function wrapper(){return R.createElement(inner,{})}'
    ),
    "hide-ctrl-g-to-edit": 'if(v&&P)p("tengu_external_editor_hint_shown",{})',
    "show-more-items-in-select-menus": 'function menu({visibleOptionCount:A=5}){return A}',
    "model-customizations": (
        'function models(){let L=[]; '
        'L.push({value:M,label:N,description:"Custom model"});return L}'
    ),
    "suppress-line-numbers": (
        'function fmt({content:C,startLine:S}){if(!C)return"";'
        'let L=C.split(/\\r?\\n/);return L.map(x=>x).join("\\n")}function next(){}'
    ),
    "auto-accept-plan-mode": (
        'function plan(){return R.createElement(Box,'
        '{title:"Ready to code?",onChange:onPick,onCancel:onCancel})}'
    ),
    "allow-custom-agent-models": (
        ',model:z.enum(MODELS).optional();'
        'let ok=K&&typeof K==="string"&&MODELS.includes(K)'
    ),
    "patches-applied-indication": 'const version=`${pkg.VERSION} (Claude Code)`;',
    "themes": "\n".join([
        'function getNames(){return{"dark":"Dark mode","light":"Light mode"}}',
        'const themeOptions=[{label:"Dark mode",value:"dark"},'
        '{label:"Light mode",value:"light"}];',
        'function pickTheme(A){switch(A){case"light":return LX9;'
        'case"dark":return CX9;default:return CX9}}',
    ]),
    "prompt-overlays": (
        'let WEBFETCH=`Fetches URLs.\\n'
        '- For GitHub URLs, prefer using the gh CLI via Bash instead '
        '(e.g., gh pr view, gh issue view, gh api).`;'
    ),
}
